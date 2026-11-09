# Standalone RAM appliance. Never import the target host's disks or services.
{ inputs, spec }:
let
  localConsole = (spec.boot_trust or "secure-boot") == "local-console";
  console = spec.console or "tty1";
  sshEnabled = spec.authorized_keys != [ ];
  runtimeSystem = inputs.nixpkgs.lib.nixosSystem {
    system = "x86_64-linux";
    modules = [
      (
        {
          config,
          lib,
          pkgs,
          modulesPath,
          ...
        }:
        let
          python = pkgs.python312.withPackages (p: [
            p.pydantic
            p.pyyaml
            p.ruamel-yaml
            p.cryptography
            p.jinja2
          ]);
          source = lib.cleanSourceWith {
            src = ../lx_administration;
            filter =
              path: type:
              type == "directory" && baseNameOf path != "__pycache__"
              || type == "regular" && !(lib.hasSuffix ".pyc" path);
          };
          runtime = pkgs.runCommand "luxnix-migration-runtime" { } ''
            mkdir -p $out/lx_administration
            cp -r ${source}/. $out/lx_administration/
          '';
          migration = pkgs.writeShellApplication {
            name = "luxnix-migration";
            runtimeInputs = [
              python
              pkgs.gitMinimal
              pkgs.nix
              config.system.build.nixos-install
              pkgs.cryptsetup
              pkgs.btrfs-progs
              pkgs.util-linux
              pkgs.rsync
              pkgs.age
              pkgs.openssl
              pkgs.coreutils
              pkgs.findutils
            ];
            text = ''
              export PYTHONPATH=${runtime}
              exec ${python}/bin/python -m lx_administration.storage.boot_setup "$@"
            '';
          };
          certificate = ./secure-boot/db.pem;
        in
        {
          imports = [
            (modulesPath + "/installer/netboot/netboot.nix")
            (modulesPath + "/profiles/minimal.nix")
          ];
          system = {
            stateVersion = "26.05";
            disableInstallerTools = true;
            tools.nixos-install.enable = true;
            tools.nixos-enter.enable = true;
          };
          # The appliance installs a preserved closure; it never rebuilds itself.
          nixpkgs.flake.setNixPath = false;
          nixpkgs.flake.setFlakeRegistry = false;
          networking = {
            hostName = "${spec.host}-migration";
            useDHCP = false;
            useNetworkd = true;
            firewall.extraCommands = lib.mkIf sshEnabled ''
              ${pkgs.iptables}/bin/iptables -A nixos-fw -i ${lib.escapeShellArg spec.interface} \
                -s ${lib.escapeShellArg spec.controller_cidr} -p tcp \
                --dport ${toString spec.policy.ssh_port} -j nixos-fw-accept
            '';
          };
          systemd = {
            network.networks."10-management" = {
              matchConfig.Name = spec.interface;
              address = [ spec.address ];
              routes = lib.optional (spec.gateway != null) {
                Gateway = spec.gateway;
              };
              linkConfig.RequiredForOnline = "routable";
            };
            generators.systemd-ssh-generator = lib.mkIf (!sshEnabled) "/dev/null";
            services = {
              # A local shell is available only after physical approval in this image.
              "getty@tty1".enable = lib.mkIf localConsole false;
              "autovt@tty1".enable = lib.mkIf localConsole false;
              "serial-getty@ttyS0".enable = lib.mkIf localConsole false;
              luxnix-migration-console = lib.mkIf localConsole {
                wantedBy = [ "multi-user.target" ];
                requires = [ "luxnix-migration-admission.service" ];
                after = [ "luxnix-migration-admission.service" ];
                serviceConfig = {
                  Type = "simple";
                  ExecStart = "${pkgs.bashInteractive}/bin/bash --login";
                  StandardInput = "tty";
                  StandardOutput = "tty";
                  StandardError = "tty";
                  TTYPath = "/dev/${console}";
                  TTYReset = true;
                  TTYVHangup = true;
                  Restart = "always";
                };
              };
              luxnix-migration-admission = {
                wantedBy = [ "multi-user.target" ];
                before = [ "sshd.service" ];
                after = lib.optional sshEnabled "sshd-keygen.service";
                requires = lib.optional sshEnabled "sshd-keygen.service";
                path = [
                  pkgs.util-linux
                  pkgs.openssh
                ];
                serviceConfig = {
                  Type = "oneshot";
                  RemainAfterExit = true;
                  StandardInput = lib.mkIf localConsole "tty";
                  StandardOutput = lib.mkIf localConsole "tty";
                  StandardError = lib.mkIf localConsole "tty";
                  TTYPath = lib.mkIf localConsole "/dev/${console}";
                  TTYReset = lib.mkIf localConsole true;
                  TimeoutStartSec = lib.mkIf localConsole "infinity";
                };
                script = ''
                  export PYTHONPATH=${runtime}
                  ${python}/bin/python -m lx_administration.storage.migration_boot admit \
                    --spec /etc/luxnix/migration.json --certificate /etc/luxnix/migration-db.pem
                  ${lib.optionalString sshEnabled ''
                    echo 'Verify this recovery SSH fingerprint through the trusted console:' > /dev/console
                    ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub > /dev/console
                  ''}
                '';
              };
              sshd = lib.mkIf sshEnabled {
                requires = [ "luxnix-migration-admission.service" ];
                after = [ "luxnix-migration-admission.service" ];
              };
            };
          };
          services.openssh = {
            enable = sshEnabled;
            openFirewall = false;
            ports = [ spec.policy.ssh_port ];
            hostKeys = [
              {
                path = "/etc/ssh/ssh_host_ed25519_key";
                type = "ed25519";
              }
            ];
            settings = {
              PasswordAuthentication = false;
              KbdInteractiveAuthentication = false;
              PermitRootLogin = "prohibit-password";
              AllowUsers = [ "root" ];
              AllowTcpForwarding = false;
              X11Forwarding = false;
            };
          };
          users.users.root = {
            hashedPassword = "!";
            openssh.authorizedKeys.keys = spec.authorized_keys;
          };
          services.getty.autologinUser = lib.mkForce null;
          swapDevices = lib.mkForce [ ];
          zramSwap.enable = lib.mkForce false;
          boot = {
            resumeDevice = lib.mkForce "";
            postBootCommands = lib.mkForce "";
            loader.systemd-boot.enable = false;
            loader.efi.canTouchEfiVariables = false;
            initrd.availableKernelModules = [
              "nvme"
              "ahci"
              "sd_mod"
              "usb_storage"
              "xhci_pci"
              "usbhid"
            ];
            supportedFilesystems = [
              "btrfs"
              "ext4"
              "vfat"
            ];
            kernelParams = [
              "console=tty0"
              "console=ttyS0,115200"
              "noresume"
              "rd.systemd.gpt_auto=0"
              "systemd.gpt_auto=0"
            ];
            uki = {
              name = "luxnix-migration-${spec.host}";
              version = spec.revision;
            };
          };
          netboot.squashfsCompression = "xz -Xdict-size 100%";
          environment = {
            systemPackages = [
              migration
              python
              pkgs.openssh
              pkgs.cryptsetup
              pkgs.btrfs-progs
              pkgs.util-linux
              pkgs.rsync
              pkgs.age
              pkgs.gitMinimal
            ];
            etc."luxnix/migration.json".text = builtins.toJSON spec;
            etc."luxnix/migration-db.pem".source = certificate;
          };
          # Target mounts, conversion, state import and reboot remain operator actions.
        }
      )
    ];
  };
in
runtimeSystem.extendModules {
  modules = [ (import ./migration-loader.nix { inherit spec runtimeSystem; }) ];
}
