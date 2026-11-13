# Standalone RAM appliance. Never import the target host's disks or services.
{ inputs, spec }:
let
  localConsole = (spec.boot_trust or "secure-boot") == "local-console";
  # Started by the trusted running host with kexec; no firmware, loader or console.
  hostKexec = (spec.boot_trust or "secure-boot") == "host-kexec";
  # Created on the host before kexec, so its fingerprint can be pinned beforehand.
  kexecHostKey = "/run/luxnix-kexec/ssh_host_ed25519_key";
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
              # bootctl holds the boot default here while the root is converted.
              pkgs.systemd
              # Keeps a conversion running when an SSH connection drops.
              pkgs.tmux
            ];
            # Verifies the plan's own source on the recovery drive, then runs it.
            text = ''
              export PYTHONPATH=${runtime}
              exec ${python}/bin/python -m lx_administration.storage.installer_handoff "$@"
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
            # Suspend would pause a running conversion; nothing may sleep here.
            targets = {
              sleep.enable = false;
              suspend.enable = false;
              hibernate.enable = false;
              hybrid-sleep.enable = false;
              suspend-then-hibernate.enable = false;
            };
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
              # Both images open a root shell on the screen only after a typed phrase.
              # The staged image asks during admission; a host-kexec image shows how to
              # connect and opens its terminal on request. Presence at the machine is
              # the credential: this image holds no account passwords.
              "getty@tty1".enable = lib.mkIf (localConsole || hostKexec) false;
              "autovt@tty1".enable = lib.mkIf (localConsole || hostKexec) false;
              "serial-getty@ttyS0".enable = lib.mkIf (localConsole || hostKexec) false;
              luxnix-migration-access = lib.mkIf hostKexec {
                wantedBy = [ "multi-user.target" ];
                after = [
                  "luxnix-migration-admission.service"
                  "sshd.service"
                ];
                path = [
                  pkgs.openssh
                  pkgs.systemd
                ];
                environment.HOME = "/root";
                serviceConfig = {
                  Type = "simple";
                  StandardInput = "tty";
                  StandardOutput = "tty";
                  StandardError = "tty";
                  TTYPath = "/dev/${console}";
                  TTYReset = true;
                  TTYVHangup = true;
                  WorkingDirectory = "/root";
                  # Leaving the terminal returns to the access screen.
                  Restart = "always";
                  RestartSec = "1s";
                };
                script = ''
                  # Typed identically on German and US keyboards.
                  phrase="LOCAL TERMINAL"
                  clear || true
                  echo "LuxNix migration environment for ${spec.host}, started remotely"
                  echo
                  if systemctl is-active --quiet sshd.service; then
                    echo "Access: ssh -p ${toString spec.policy.ssh_port} root@${builtins.head (lib.splitString "/" spec.address)}"
                    echo "Allowed from: ${spec.controller_cidr}, administrator keys only"
                    echo "Host key: $(ssh-keygen -lf ${kexecHostKey}.pub)"
                  else
                    echo "SSH is closed: this environment did not receive the host key"
                    echo "pinned by migration-boot kexec. Use the terminal on this screen."
                  fi
                  echo
                  echo "For a root terminal on this screen, type $phrase and press Enter."
                  while true; do
                    # A closed or hung-up terminal restarts this screen.
                    IFS= read -r answer || exit 1
                    if [ "$answer" = "$phrase" ]; then break; fi
                    echo "Not opened. Type $phrase exactly."
                  done
                  echo "Root terminal in RAM; disks are unchanged until you run a migration step."
                  echo "Leave with exit to return to the access screen."
                  exec ${pkgs.bashInteractive}/bin/bash --login
                '';
              };
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
                  ${lib.optionalString (sshEnabled && !hostKexec) ''
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
          services = {
            # Closing the lid or an idle timeout must not try to sleep either.
            logind.settings.Login = {
              HandleLidSwitch = "ignore";
              HandleLidSwitchExternalPower = "ignore";
              HandleLidSwitchDocked = "ignore";
              HandleSuspendKey = "ignore";
              HandleHibernateKey = "ignore";
              IdleAction = "ignore";
            };
            getty.autologinUser = lib.mkForce null;
            openssh = {
              enable = sshEnabled;
              openFirewall = false;
              ports = [ spec.policy.ssh_port ];
              hostKeys = [
                {
                  path = if hostKexec then kexecHostKey else "/etc/ssh/ssh_host_ed25519_key";
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
          };
          users.users.root = {
            hashedPassword = "!";
            openssh.authorizedKeys.keys = spec.authorized_keys;
          };
          # The root is a fresh tmpfs; the recovery drive mounts here.
          systemd.tmpfiles.rules = [ "d /recovery 0700 root root - -" ];
          swapDevices = lib.mkForce [ ];
          zramSwap.enable = lib.mkForce false;
          # Kernel notices after boot must not scroll the access screen and its
          # terminal away; errors still reach the screen.
          boot.kernel.sysctl."kernel.printk" = lib.mkIf hostKexec "3 4 1 3";
          # Every fleet host uses this console layout; SSH sessions are unaffected.
          console.keyMap = "de";
          boot = {
            resumeDevice = lib.mkForce "";
            postBootCommands = lib.mkForce "";
            loader.systemd-boot.enable = false;
            loader.efi.canTouchEfiVariables = false;
            # The kexec command appends /luxnix-kexec to the initrd: the SSH host key it
            # pinned and a rule keeping the management interface's name. systemd moves
            # /run into the running system, where sshd and udev use them.
            initrd.systemd.services.luxnix-kexec-identity = lib.mkIf hostKexec {
              wantedBy = [ "initrd.target" ];
              before = [ "initrd-switch-root.target" ];
              unitConfig.DefaultDependencies = false;
              serviceConfig.Type = "oneshot";
              script = ''
                if [ -d /luxnix-kexec ]; then
                  mkdir -p -m 0700 /run/luxnix-kexec /run/systemd/network
                  cp -p /luxnix-kexec/ssh_host_ed25519_key /luxnix-kexec/ssh_host_ed25519_key.pub \
                    /luxnix-kexec/identity.json /run/luxnix-kexec/
                  chmod 0600 /run/luxnix-kexec/ssh_host_ed25519_key
                  cp /luxnix-kexec/10-luxnix-management.link /run/systemd/network/
                fi
              '';
            };
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
            # The last console receives boot status and prompts: the selected one.
            # The EFI loader layer sets its own; this order serves migration-boot kexec.
            kernelParams =
              (
                if console == "ttyS0" then
                  [
                    "console=tty0"
                    "console=ttyS0,115200"
                  ]
                else
                  [
                    "console=ttyS0,115200"
                    "console=tty0"
                  ]
              )
              ++ [
                "systemd.show_status=1"
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
              # Operators start their own session for long steps over SSH.
              pkgs.tmux
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
  modules = [
    (import ./migration-loader.nix { inherit spec runtimeSystem; })
    (
      { pkgs, ... }:
      {
        # The runtime itself, without the EFI loader: started by migration-boot kexec.
        system.build.kexecBundle =
          let
            runtime = runtimeSystem.config;
          in
          pkgs.runCommand "luxnix-migration-kexec-${spec.host}" { } ''
            mkdir $out
            ln -s ${runtime.system.build.kernel}/${runtime.system.boot.loader.kernelFile} $out/kernel
            ln -s ${runtime.system.build.netbootRamdisk}/initrd $out/initrd
            echo -n ${pkgs.lib.escapeShellArg "init=${runtime.system.build.toplevel}/init ${toString runtime.boot.kernelParams}"} > $out/cmdline
            cp ${pkgs.writeText "manifest.json" (builtins.toJSON spec)} $out/manifest.json
          '';
      }
    )
  ];
}
