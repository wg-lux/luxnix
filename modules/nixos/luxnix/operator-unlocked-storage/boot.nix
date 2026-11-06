{
  config,
  lib,
  pkgs,
  options,
  utils ? config._module.args.utils,
  ...
}:
let
  cfg = config.luxnix.storage.operatorUnlocked;
  remote = cfg.remoteUnlock;
  unlockCommand = pkgs.writeShellScript "luxnix-root-unlock" ''
    echo 'Enter the disk recovery passphrase. This connection cannot run other commands.'
    # A previous attempt may still be deriving its key when SSH reconnects.
    while true; do
      for request in /run/systemd/ask-password/ask.*; do
        if test -f "$request"; then
          exec ${config.boot.initrd.systemd.package}/bin/systemd-tty-ask-password-agent --query
        fi
      done
      ${pkgs.coreutils}/bin/sleep 1
    done
  '';
  enabled = cfg.enable && cfg.layout == "boot-luks";
  recoveryHint = "Problems? Press Ctrl+Alt+Del and choose an older system in the menu.";
  mountUnit = path: "${utils.escapeSystemdPath path}.mount";
  luks =
    lib.concatLists (
      lib.mapAttrsToList (
        _: disk:
        lib.mapAttrsToList (_: p: p.content) (
          lib.filterAttrs (_: p: p.content != null && p.content.type == "luks") disk.content.partitions
        )
      ) (lib.attrByPath [ "disko" "devices" "disk" ] { } config)
    )
    ++ lib.mapAttrsToList (_: array: array.content) (
      lib.filterAttrs (_: array: array.content != null && array.content.type == "luks") (
        lib.attrByPath [ "disko" "devices" "mdadm" ] { } config
      )
    );
  secondary = builtins.filter (
    v:
    !v.initrdUnlock
    && (
      v.content == null
      || v.content.type != "swap"
      || lib.any (s: s.device == "/dev/mapper/${v.name}") config.swapDevices
    )
  ) luks;
  keyFile = v: "/etc/luks-keys/${v.name}.key";
  # Use the evaluated filesystem graph, including host bind mounts and subvolumes.
  app = lib.attrByPath [ "services" "luxnix" "lxAnnotateLocal" ] { } config;
  runtime = app.runtime or { };
  appPaths = lib.optionals (app.enable or false) (
    [
      runtime.encryptedDataDir
      runtime.modelTrainingStagingRoot
    ]
    ++ lib.optional (
      runtime.streamableServing.externalStorageRoot != null
    ) runtime.streamableServing.externalStorageRoot

  );
  paths = lib.unique (
    [
      "/"
      "/nix"
      "/home"
      "/persist"
      "/etc/secrets"
      "/var/log"
      "/var/tmp"
    ]
    ++ appPaths
    ++ lib.concatLists (builtins.attrValues cfg.guardedServices)
  );
  mountsFor =
    paths:
    builtins.filter (
      mount: lib.any (path: mount == "/" || path == mount || lib.hasPrefix "${mount}/" path) paths
    ) (builtins.attrNames config.fileSystems);
  volumeMounts =
    v:
    lib.optional (v.content != null && (v.content.mountpoint or null) != null) v.content.mountpoint
    ++ map (s: s.mountpoint) (
      builtins.attrValues (if v.content == null then { } else v.content.subvolumes or { })
    );
  # Btrfs format arguments name every additional member mapping.
  membersFor =
    mount:
    builtins.filter (
      v:
      lib.any (
        owner:
        builtins.elem mount (volumeMounts owner)
        && (v.name == owner.name || builtins.elem "/dev/mapper/${v.name}" (owner.content.extraArgs or [ ]))
      ) secondary
    ) secondary;
  dataMounts = lib.unique (lib.concatMap volumeMounts secondary);
  allMounts = lib.unique (mountsFor paths ++ dataMounts);
  storageSpec =
    requiredPaths: mounts: keys:
    pkgs.writeText "boot-storage.json" (
      builtins.toJSON {
        mounts = lib.genAttrs mounts (p: {
          inherit (config.fileSystems.${p}) device fsType;
          subvolume = lib.findFirst (o: lib.hasPrefix "subvol=" o) null config.fileSystems.${p}.options;
        });
        keys = map (v: {
          path = keyFile v;
          inherit (v) device;
          mapping = v.name;
        }) keys;
        paths = requiredPaths;
      }
    );
  spec = storageSpec paths allMounts secondary;
  checker = pkgs.runCommand "boot-storage-checker" { } ''
    mkdir -p "$out"
    cp ${../../../../lx_administration/storage/boot.py} "$out/boot.py"
    cp ${../../../../lx_administration/storage/boot_password.py} "$out/boot_password.py"
    cp ${../../../../lx_administration/storage/cutover.py} "$out/cutover.py"
    cp ${../../../../lx_administration/secret_storage.py} "$out/secret_storage.py"
  '';
  verifier = pkgs.writeShellApplication {
    name = "luxnix-verify-boot-storage";
    runtimeInputs = [
      pkgs.python3
      pkgs.util-linux
      pkgs.btrfs-progs
      pkgs.cryptsetup
    ];
    text = ''
      exec python3 ${checker}/boot.py ${spec} "$@"
    '';
  };
  setupPassword = pkgs.writeShellApplication {
    name = "luxnix-setup-boot-password";
    runtimeInputs = [
      pkgs.python3
      pkgs.util-linux
      pkgs.cryptsetup
    ];
    text = ''
      exec python3 ${checker}/boot_password.py \
        --device ${lib.escapeShellArg config.boot.initrd.luks.devices.cryptroot.device} "$@"
    '';
  };
  setupRoot = pkgs.writeShellApplication {
    name = "luxnix-setup-root-encryption";
    runtimeInputs = [
      pkgs.python3
      pkgs.util-linux
      pkgs.btrfs-progs
      pkgs.cryptsetup
    ];
    text = ''
      usage() {
        echo 'Usage: luxnix-setup-root-encryption [--setup-password]'
        echo 'Inspect the running root against this candidate; plaintext root requires reviewed in-place encryption.'
        echo 'Preview in-place encryption from the reviewed LuxNix checkout: devenv tasks run boot-storage:setup'
        echo '--setup-password verifies an existing LUKS password only after the root check succeeds.'
        echo 'Never formats disks, opens mappings, changes keyslots or activates a generation.'
      }
      if [ "$#" -gt 1 ]; then usage >&2; exit 2; fi
      case "''${1:-}" in
        --help) usage; exit 0 ;;
        ""|--setup-password) ;;
        *) usage >&2; exit 2 ;;
      esac
      if [ "$EUID" -ne 0 ]; then echo 'Run with sudo to inspect LUKS mappings.' >&2; exit 1; fi
      printf 'Candidate host: %s\nConfigured LUKS device: %s\n' \
        ${lib.escapeShellArg config.networking.hostName} \
        ${lib.escapeShellArg config.boot.initrd.luks.devices.cryptroot.device}
      python3 ${checker}/boot.py ${spec} --root-setup
      if [ "''${1:-}" = --setup-password ]; then
        exec ${lib.getExe setupPassword}
      fi
    '';
  };
  check = name: "luxnix-storage-check-${name}";
  guard =
    requiredPaths:
    let
      mounts = mountsFor requiredPaths;
    in
    {
      requires = map mountUnit mounts;
      after = map mountUnit mounts;
      bindsTo = map mountUnit mounts;
      unitConfig.RequiresMountsFor = requiredPaths;
    };
in
{
  options.luxnix.storage.operatorUnlocked.remoteUnlock = {
    enable = lib.mkEnableOption "operator-only SSH unlock on the early-boot management network";
    interface = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Exact wired management interface name.";
    };
    kernelModules = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Verified management NIC drivers required before root unlock.";
    };
    address = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Static early-boot management address with prefix length.";
    };
    gateway = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Optional management gateway.";
    };
    allowedSources = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Numeric management client addresses or CIDRs allowed to authenticate.";
    };
    authorizedKeys = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Dedicated operator public keys, not inherited login keys.";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 2222;
      description = "Dedicated early-boot SSH port.";
    };
    hostKey = lib.mkOption {
      type = lib.types.str;
      default = "/etc/luxnix/initrd-ssh/ssh_host_ed25519_key";
      description = "Dedicated host identity copied into initrd; never use a login host key.";
    };
  };
  config = lib.mkIf enabled (
    lib.mkMerge [
      {
        assertions = [
          {
            assertion =
              cfg.unlockMethod == "passphrase"
              && !(lib.attrByPath [ "luxnix" "tpmReleaseClient" "enable" ] false config);
            message = "Boot LUKS uses independent root unlock; alternative disk-unlock backends are retired for new enrollment.";
          }

          {
            assertion = lib.all (
              name:
              config.systemd.services.${name}.enable
              && (
                (config.systemd.services.${name}.serviceConfig.ExecStart or "") != ""
                || (config.systemd.services.${name}.script or "") != ""
              )
            ) (builtins.attrNames cfg.guardedServices);
            message = "Every boot-storage guarded consumer must define an enabled executable service.";
          }
          {
            assertion = lib.length (builtins.filter (v: v.initrdUnlock) luks) == 1;
            message = "Boot storage requires exactly one initial root LUKS unlock.";
          }
          {
            assertion = !config.luxnix.storage.loginAccess.enable;
            message = "Boot LUKS replaces login-triggered storage unlock; disable loginAccess.";
          }
          {
            assertion = !config.services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.enable;
            message = "Boot LUKS replaces the application managedEncryptedData container.";
          }
          {
            assertion = lib.all (v: !(builtins.hasAttr v.name config.boot.initrd.luks.devices)) secondary;
            message = "Secondary keys must never be consumed or copied by the initrd.";
          }
          {
            assertion = config.boot.plymouth.enable;
            message = "Boot LUKS asks for the root passphrase on the Plymouth splash screen; do not force boot.plymouth.enable off.";
          }
          {
            assertion =
              config.boot.initrd.luks.devices.cryptroot.keyFile == null
              && lib.all (
                option:
                !(lib.any (prefix: lib.hasPrefix prefix option) [
                  "fido2-"
                  "tpm2-"
                  "pkcs11-"
                  "keyfile-"
                  "try-empty-password"
                  "headless"
                ])
              ) config.boot.initrd.luks.devices.cryptroot.crypttabExtraOpts;
            message = "Root unlock must prompt the operator; remove USB/key-file, token and unattended unlock options.";
          }
        ];
        # The passphrase prompt follows the storage layout on every rebuild.
        boot.plymouth.enable = true;
        luxnix = lib.optionalAttrs (options.luxnix ? vault) {
          vault.server.managedTls.encryptedStorage = lib.mkForce false;
        };
        # The splash prompt waits without a time or attempt limit: an exhausted
        # prompt leaves no bootable system. Recovery is a restart into the boot
        # menu (Ctrl+Alt+Del), which then waits for an older generation choice.
        boot.initrd = {
          luks.devices.cryptroot.crypttabExtraOpts = [
            "timeout=0"
            "tries=0"
          ];
          systemd = {
            enable = true;
            initrdBin = [ pkgs.cryptsetup ];
            storePaths = [
              "${config.boot.initrd.systemd.package}/bin/bootctl"
              (lib.getExe' config.boot.plymouth.package "plymouth")
            ];
            # ctrl-alt-del.target aliases reboot.target in the initrd.
            services.luxnix-reboot-to-boot-menu = {
              description = "Keep the boot menu open after a restart from the disk password screen";
              wantedBy = [ "reboot.target" ];
              before = [ "systemd-reboot.service" ];
              unitConfig.DefaultDependencies = false;
              serviceConfig = {
                Type = "oneshot";
                ExecStart = "${config.boot.initrd.systemd.package}/bin/bootctl set-timeout-oneshot menu-force";
              };
            };
            services.luxnix-unlock-recovery-hint = {
              description = "Show the restart hint on the disk password screen";
              wantedBy = [ "initrd.target" ];
              after = [ "plymouth-start.service" ];
              conflicts = [ "initrd-switch-root.target" ];
              before = [ "initrd-switch-root.target" ];
              unitConfig = {
                DefaultDependencies = false;
                ConditionPathExists = "/run/plymouth/pid";
              };
              serviceConfig = {
                Type = "oneshot";
                RemainAfterExit = true;
                ExecStart = "${lib.getExe' config.boot.plymouth.package "plymouth"} display-message --text=${lib.escapeShellArg recoveryHint}";
                ExecStop = "${lib.getExe' config.boot.plymouth.package "plymouth"} hide-message --text=${lib.escapeShellArg recoveryHint}";
              };
            };
          };
        };
        # systemd's stage-2 generator reads these keys only after encrypted root opens.
        environment.etc.crypttab.text =
          lib.concatMapStringsSep "\n" (
            v: "${v.name} ${v.device} ${keyFile v} luks,nofail,headless,x-systemd.device-timeout=30s"
          ) secondary
          + "\n";
        # Disk recovery always needs these, also from a damaged generation.
        environment.systemPackages = [
          pkgs.cryptsetup
          verifier
          setupPassword
          setupRoot
        ];
        systemd.services = lib.mkMerge [
          (lib.listToAttrs (
            map (
              v:
              lib.nameValuePair "systemd-cryptsetup@${utils.escapeSystemdPath v.name}" {
                overrideStrategy = "asDropin";
                unitConfig.RequiresMountsFor = [ "/etc/luks-keys" ];
                serviceConfig = {
                  TimeoutStartSec = "45s";
                  ExecStartPre = "${pkgs.python3}/bin/python3 ${checker}/boot.py --key ${keyFile v}";
                };
                path = [ pkgs.util-linux ];
              }
            ) secondary
          ))
          (lib.mapAttrs (
            name: requiredPaths:
            lib.mkMerge [
              (guard requiredPaths)
              (lib.mkIf (!cfg.autoStartProtectedServices) {
                wantedBy = lib.mkForce [ ];
              })
              {
                requires = [ "${check name}.service" ];
                after = [ "${check name}.service" ];
              }
            ]
          ) cfg.guardedServices)
          (lib.mapAttrs' (
            name: requiredPaths:
            lib.nameValuePair (check name) (
              lib.recursiveUpdate (guard requiredPaths) {
                description = "Verify mounted encrypted storage before ${name}; see storage migration runbook";
                path = [
                  pkgs.util-linux
                  pkgs.cryptsetup
                ];
                serviceConfig = {
                  Type = "oneshot";
                  TimeoutStartSec = "45s";
                  # Actual crypttab opening tests keys at boot. Avoid repeating the
                  # expensive key derivation for every already-mounted consumer.
                  ExecStart = "${pkgs.python3}/bin/python3 ${checker}/boot.py ${
                    storageSpec requiredPaths (mountsFor requiredPaths) (
                      lib.unique (lib.concatMap membersFor (mountsFor requiredPaths))
                    )
                  } --mounted-storage";
                };
              }
            )
          ) cfg.guardedServices)
        ];
        # Data failures do not hide the console behind an unbounded graphical wait.
        fileSystems =
          lib.genAttrs dataMounts (mount: {
            options = [
              "nofail"
              "x-systemd.device-timeout=30s"
            ]
            ++ map (v: "x-systemd.requires=systemd-cryptsetup@${utils.escapeSystemdPath v.name}.service") (
              membersFor mount
            );
          })
          // {
            "/".options = [ "x-systemd.device-timeout=0" ];
          };
        systemd.sleep.settings.Sleep = {
          AllowHibernation = false;
          AllowHybridSleep = false;
          AllowSuspendThenHibernate = false;
        };
      }
      (lib.mkIf remote.enable {
        assertions = [
          {
            assertion =
              builtins.match "[A-Za-z0-9_.-]+" remote.interface != null
              && builtins.match "[0-9a-fA-F.:]+/[0-9]+" remote.address != null;
            message = "Remote root unlock requires an explicit management interface and static address.";
          }
          {
            assertion =
              remote.authorizedKeys != [ ]
              && lib.all (
                k: builtins.match "ssh-ed25519 [A-Za-z0-9+/=]+( .*)?" k != null && !(lib.hasInfix "\n" k)
              ) remote.authorizedKeys;
            message = "Remote unlock requires dedicated Ed25519 operator public keys.";
          }
          {
            assertion =
              remote.allowedSources != [ ]
              && lib.all (s: builtins.match "[0-9a-fA-F.:/]+" s != null) remote.allowedSources;
            message = "Remote unlock requires explicit numeric management client addresses or CIDRs.";
          }
          {
            assertion = remote.hostKey == "/etc/luxnix/initrd-ssh/ssh_host_ed25519_key";
            message = "Remote unlock must use its dedicated host identity, never ordinary login keys.";
          }
          {
            assertion = remote.kernelModules != [ ];
            message = "Specify the verified early-boot management NIC driver modules.";
          }
        ];
        boot.initrd = {
          inherit (remote) kernelModules;
          systemd = {
            network = {
              enable = true;
              networks."10-luxnix-unlock" = {
                matchConfig.Name = remote.interface;
                address = [ remote.address ];
                networkConfig = {
                  DHCP = "no";
                  LinkLocalAddressing = "no";
                  IPv6AcceptRA = false;
                };
                routes = lib.optional (remote.gateway != null) { Gateway = remote.gateway; };
              };
            };
            services.sshd = {
              # The configured address can appear after network.target.
              unitConfig.StartLimitIntervalSec = 0;
              serviceConfig.RestartSec = "5s";
            };
            storePaths = [ unlockCommand ];
          };
          network.ssh = {
            enable = true;
            inherit (remote) port;
            hostKeys = [ remote.hostKey ];
            authorizedKeyFiles = lib.mkForce [ ];
            authorizedKeys = lib.mkForce (
              map (
                key:
                ''restrict,pty,from="${lib.concatStringsSep "," remote.allowedSources}",command="${unlockCommand}" ${key}''
              ) remote.authorizedKeys
            );
            extraConfig = ''
              ListenAddress ${lib.head (lib.splitString "/" remote.address)}
              PermitRootLogin forced-commands-only
              AllowUsers root
              DisableForwarding yes
              PermitUserEnvironment no
              PermitUserRC no
              MaxAuthTries 3
              ForceCommand ${unlockCommand}
            '';
          };
        };
      })
    ]
  );
}
