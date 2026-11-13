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
  usb = cfg.usbKeyUnlock;
  # systemd's crypttab syntax: key file path on the filesystem with this UUID.
  usbKeyFile = "/${usb.keyPath}:UUID=${usb.filesystemUuid}";
  access = (import ../../../../lib/network-access { inherit lib; }).networkAccess;
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
  recoveryHint = "Problems? Press Ctrl+Alt+Del and choose recovery media or a compatible system.";
  refusePlaintext = ''
    echo 'Root has no LUKS2 header; this generation requires encrypted root.' >&2
    echo 'Choose a generation matching this disk or boot recovery media.' >&2
    exit 1
  '';
  # Disabled by default: without a LUKS2 header there is nothing to authenticate.
  # A missing header alone is not evidence of a plaintext filesystem, and low-level
  # probing rejects ambiguous signatures and unreadable devices.
  plaintextBridge = ''
    if ! filesystem=$(blkid --probe --output value --match-tag TYPE "$device"); then
      echo 'Cannot identify root filesystem; refusing plaintext fallback' >&2
      exit 1
    fi
    if [ "$filesystem" != ${lib.escapeShellArg config.fileSystems."/".fsType} ]; then
      echo "Root is neither LUKS2 nor the configured plaintext filesystem; refusing to mount it" >&2
      exit 1
    fi
    echo 'Booting plaintext root for migration; protected storage remains unavailable.' >&2
    exec dmsetup create cryptroot --uuid LUXNIX-PLAINTEXT-ROOT \
      --table "0 $(blockdev --getsz "$device") linear $(readlink -f "$device") 0"
  '';
  rootDevice = pkgs.writeShellApplication {
    name = "luxnix-root-device";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.cryptsetup
      pkgs.lvm2
      pkgs.util-linux
      config.boot.initrd.systemd.package
    ];
    text = ''
      if [ "$1" = detach ]; then
        if [ "$(dmsetup info -c --noheadings -o uuid cryptroot 2>/dev/null)" = LUXNIX-PLAINTEXT-ROOT ]; then
          exec dmsetup remove cryptroot
        fi
        exec systemd-cryptsetup detach cryptroot
      fi
      # Consume NixOS's crypttab, preserving its complete unlock options.
      while read -r name device key opts; do
        [ "$name" = cryptroot ] || continue
        # The crypttab generator mounts a key device here; this unit replaces
        # only its attach command, so resolve the path the same way. A stick
        # that is absent or rejected falls back to the passphrase prompt.
        case "$key" in
          *:*) key="/run/systemd/cryptsetup/keydev-$name/''${key%%:*}" ;;
        esac
        if cryptsetup isLuks --type luks2 "$device"; then
          # Failed unlock must never fall through to plaintext handling.
          exec systemd-cryptsetup attach "$name" "$device" "$key" "$opts"
        fi
        ${if cfg.plaintextRootBridge then plaintextBridge else refusePlaintext}
      done < /etc/crypttab
      echo 'Missing cryptroot entry in initrd crypttab' >&2
      exit 1
    '';
  };
  mountUnit = path: "${utils.escapeSystemdPath path}.mount";
  luksContents =
    values:
    map (v: v.content) (builtins.filter (v: v.content != null && v.content.type == "luks") values);
  luks =
    lib.concatMap (disk: luksContents (builtins.attrValues disk.content.partitions)) (
      builtins.attrValues (lib.attrByPath [ "disko" "devices" "disk" ] { } config)
    )
    ++ luksContents (builtins.attrValues (lib.attrByPath [ "disko" "devices" "mdadm" ] { } config));
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
  storageCommand =
    name: inputs: text:
    pkgs.writeShellApplication {
      inherit name text;
      runtimeInputs = [
        pkgs.python3
        pkgs.util-linux
      ]
      ++ inputs;
    };
  verifier = storageCommand "luxnix-verify-boot-storage" [ pkgs.btrfs-progs pkgs.cryptsetup ] ''
    exec python3 ${checker}/boot.py ${spec} "$@"
  '';
  operatorStorage =
    storageCommand "luxnix-operator-storage"
      [
        pkgs.btrfs-progs
        pkgs.cryptsetup
        pkgs.systemd
      ]
      ''
        if [ "$EUID" -ne 0 ]; then echo 'Run with sudo.' >&2; exit 1; fi
        if [ "$#" -ne 1 ]; then
          echo 'Usage: luxnix-operator-storage start|open|status' >&2; exit 2
        fi
        case "$1" in
          status)
            exec python3 ${checker}/boot.py ${spec}
            ;;
          start|open)
            # A running system already unlocked root. Verify its actual backing
            # before allowing secondary keys or protected consumers to be used.
            python3 ${checker}/boot.py ${storageSpec [ "/" ] [ "/" ] [ ]}
            ${lib.optionalString (secondary != [ ]) ''
              systemctl --no-ask-password start ${
                lib.escapeShellArgs (
                  map (v: "systemd-cryptsetup@${utils.escapeSystemdPath v.name}.service") secondary
                )
              }
            ''}
            ${lib.optionalString (dataMounts != [ ]) ''
              systemctl --no-ask-password start ${lib.escapeShellArgs (map mountUnit dataMounts)}
            ''}
            python3 ${checker}/boot.py ${spec}
            ${lib.optionalString (cfg.startupServices != [ ]) ''
              if [ "$1" = start ]; then
                systemctl --no-ask-password start ${
                  lib.escapeShellArgs (map (name: "${name}.service") cfg.startupServices)
                }
              fi
            ''}
            echo 'Encrypted root and secondary storage verified.'
            ;;
          *) echo 'Usage: luxnix-operator-storage start|open|status' >&2; exit 2 ;;
        esac
      '';
  setupPassword = storageCommand "luxnix-setup-boot-password" [ pkgs.cryptsetup ] ''
    exec python3 ${checker}/boot_password.py \
      --device ${lib.escapeShellArg config.boot.initrd.luks.devices.cryptroot.device} "$@"
  '';
  # Shipped on every boot-LUKS host: the identity must exist before the first
  # generation that enables remote unlock can install its initrd.
  setupRemoteUnlock =
    storageCommand "luxnix-setup-remote-unlock"
      [
        pkgs.btrfs-progs
        pkgs.coreutils
        pkgs.cryptsetup
        pkgs.openssh
      ]
      ''
        if [ "$#" -ne 0 ]; then echo 'Usage: sudo luxnix-setup-remote-unlock' >&2; exit 2; fi
        if [ "$EUID" -ne 0 ]; then echo 'Run with sudo.' >&2; exit 1; fi
        key=${lib.escapeShellArg remote.hostKey}
        # The private key is only ever written to verified encrypted root.
        python3 ${checker}/boot.py ${storageSpec [ "/" ] [ "/" ] [ ]}
        if [ -L "$key" ]; then
          echo "$key is a symbolic link; refusing to use it." >&2; exit 1
        fi
        if [ -e "$key" ]; then
          echo "Keeping the existing early-boot host identity: $key"
        else
          umask 077
          mkdir -p "$(dirname "$key")"
          ssh-keygen -q -t ed25519 -N "" \
            -C ${lib.escapeShellArg "initrd-unlock@${config.networking.hostName}"} -f "$key"
          # Only the private key is copied into the initrd.
          rm -f "$key.pub"
          sync "$key"
          echo "Created the early-boot host identity: $key"
        fi
        public=$(ssh-keygen -y -P "" -f "$key")
        case "$public" in
          'ssh-ed25519 '*) ;;
          *) echo "$key is not an Ed25519 key; remote unlock would refuse it." >&2; exit 1 ;;
        esac
        echo 'Pin this line in known_hosts on every operator computer and jump host:'
        ${
          if remote.address == "" then
            ''echo "[<early-boot address>]:${toString remote.port} $public"''
          else
            ''echo "[${lib.head (lib.splitString "/" remote.address)}]:${toString remote.port} $public"''
        }
        ${lib.optionalString (!remote.enable) ''
          echo 'Remote unlock is not enabled in this generation; enable it in the host inventory next.'
        ''}
      '';
  # Shipped on every boot-LUKS host so the stick is enrolled before the first
  # generation that waits for it.
  setupUsbUnlock =
    storageCommand "luxnix-setup-usb-unlock"
      [
        pkgs.btrfs-progs
        pkgs.coreutils
        pkgs.cryptsetup
      ]
      ''
        if [ "$#" -ne 1 ]; then
          echo 'Usage: sudo luxnix-setup-usb-unlock <USB partition, e.g. /dev/sdb1>' >&2; exit 2
        fi
        if [ "$EUID" -ne 0 ]; then echo 'Run with sudo.' >&2; exit 1; fi
        partition=$(readlink -f "$1")
        if [ ! -b "$partition" ]; then echo "$1 is not a block device." >&2; exit 1; fi
        parent=$(lsblk -no PKNAME "$partition" | head -n 1)
        disk="/dev/''${parent:-$(basename "$partition")}"
        if [ "$(lsblk -dno TRAN "$disk")" != usb ]; then
          echo "$disk is not a USB device; the key belongs on removable media only." >&2; exit 1
        fi
        filesystem=$(blkid -p -o value -s TYPE "$partition")
        case "$filesystem" in
          ext4|vfat) ;;
          *) echo "Unsupported filesystem '$filesystem'; use an existing ext4 or vfat stick. Nothing is formatted." >&2; exit 1 ;;
        esac
        uuid=$(blkid -p -o value -s UUID "$partition")
        directory=$(mktemp -d /run/luxnix-usb-key.XXXXXX)
        mount -o nosuid,nodev,noexec "$partition" "$directory"
        trap 'umount "$directory" && rmdir "$directory"' EXIT
        key="$directory"/${lib.escapeShellArg usb.keyPath}
        mkdir -p "$(dirname "$key")"
        python3 ${checker}/boot_password.py \
          --device ${lib.escapeShellArg config.boot.initrd.luks.devices.cryptroot.device} \
          --enroll-key-file "$key"
        sync
        echo 'Anyone holding this stick can unlock this disk. Set in the host inventory:'
        echo "  storage.operatorUnlocked.usbKeyUnlock.enable: \"true\""
        echo "  storage.operatorUnlocked.usbKeyUnlock.filesystemUuid: '\"$uuid\"'"
        echo "  storage.operatorUnlocked.usbKeyUnlock.fsType: '\"$filesystem\"'"
      '';
  setupRoot = storageCommand "luxnix-setup-root-encryption" [ pkgs.btrfs-progs pkgs.cryptsetup ] ''
    usage() {
      echo 'Usage: luxnix-setup-root-encryption [--setup-password]'
      echo 'Inspect the running root against this candidate; plaintext root requires reviewed in-place encryption.'
      echo 'Preserve this installation with in-place encryption: devenv shell luxnix migrate'
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
      type = lib.types.listOf access.cidr;
      # Standalone imports (VM tests) lack the network-access module.
      default =
        if options ? luxnix.networkAccess then config.luxnix.networkAccess.earlyBootSources else [ ];
      defaultText = lib.literalExpression "config.luxnix.networkAccess.earlyBootSources";
      description = "Management client networks in CIDR notation allowed to authenticate.";
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
  options.luxnix.storage.operatorUnlocked.usbKeyUnlock = {
    enable = lib.mkEnableOption ''
      unlocking root from a key file on an enrolled USB stick. The stick is a
      bearer credential: whoever holds it and the machine reads the disk. Without
      the stick the passphrase prompt appears as before
    '';
    filesystemUuid = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Filesystem UUID of the enrolled stick, printed by luxnix-setup-usb-unlock.";
    };
    fsType = lib.mkOption {
      type = lib.types.enum [
        "ext4"
        "vfat"
      ];
      default = "vfat";
      description = "Filesystem of the enrolled stick; its driver is added to the initrd.";
    };
    keyPath = lib.mkOption {
      type = lib.types.str;
      default = "luxnix/${config.networking.hostName}.luks-key";
      description = "Key file path relative to the stick's filesystem; one file per host.";
    };
    timeoutSeconds = lib.mkOption {
      type = lib.types.ints.between 5 120;
      default = 15;
      description = "How long boot waits for the stick before asking for the passphrase.";
    };
  };
  config = lib.mkIf enabled (
    lib.mkMerge [
      (lib.optionalAttrs (options ? roles.managed-secrets) {
        # Disk migration never creates a replacement application encryption key.
        roles.managed-secrets.customSecrets.lx_annotate_master_key_local.generator =
          lib.mkIf
            (
              (app.enable or false)
              && runtime.autoGenerateMasterKey
              && !runtime.sopsMasterKey.enable
              && (
                runtime.masterKeyFile == null || runtime.masterKeyFile == runtime.autoGeneratedMasterKeyFilePath
              )
            )
            (
              lib.mkForce "echo 'Missing application master key: restore the existing key before startup' >&2; exit 1"
            );
      })
      {
        assertions = [
          {
            assertion =
              config.boot.initrd.luks.devices.cryptroot.header == null
              && builtins.elem config.fileSystems."/".fsType [
                "btrfs"
                "ext4"
                "xfs"
              ];
            message = "Root detection requires an on-device LUKS2 header and a Btrfs, ext4 or XFS filesystem.";
          }
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
            assertion = lib.all (v: !(builtins.hasAttr v.name config.boot.initrd.luks.devices)) secondary;
            message = "Secondary keys must never be consumed or copied by the initrd.";
          }
          {
            assertion = config.boot.plymouth.enable;
            message = "Boot LUKS asks for the root passphrase on the Plymouth splash screen; do not force boot.plymouth.enable off.";
          }
          {
            assertion =
              config.boot.initrd.luks.devices.cryptroot.keyFile == (if usb.enable then usbKeyFile else null)
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
            message = "Root unlock must prompt the operator; remove key-file, token and unattended unlock options. The only exception is luxnix.storage.operatorUnlocked.usbKeyUnlock.";
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
              (lib.getExe rootDevice)
              (lib.getExe' pkgs.util-linux "blkid")
              (lib.getExe' pkgs.util-linux "blockdev")
              (lib.getExe' pkgs.lvm2 "dmsetup")
              pkgs.runtimeShell
              "${config.boot.initrd.systemd.package}/bin/bootctl"
              (lib.getExe' config.boot.plymouth.package "plymouth")
            ];
            # Retain the crypttab generator's device dependencies, lifetime and
            # shutdown ordering; replace only its attach/detach implementation.
            services = {
              "systemd-cryptsetup@cryptroot" = {
                overrideStrategy = "asDropin";
                serviceConfig = {
                  ExecStart = [
                    ""
                    "${lib.getExe rootDevice} attach"
                  ];
                  ExecStop = [
                    ""
                    "${lib.getExe rootDevice} detach"
                  ];
                };
              };
              # ctrl-alt-del.target aliases reboot.target in the initrd.
              luxnix-reboot-to-boot-menu = {
                description = "Keep the boot menu open after a restart from the disk password screen";
                wantedBy = [ "reboot.target" ];
                before = [ "systemd-reboot.service" ];
                unitConfig.DefaultDependencies = false;
                serviceConfig = {
                  Type = "oneshot";
                  ExecStart = "${config.boot.initrd.systemd.package}/bin/bootctl set-timeout-oneshot menu-force";
                };
              };
              luxnix-unlock-recovery-hint = {
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
          setupRemoteUnlock
          setupUsbUnlock
          operatorStorage
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
      }
      (lib.mkIf usb.enable {
        assertions = [
          {
            assertion = builtins.match "[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}|[0-9a-f-]{36}" usb.filesystemUuid != null;
            message = "USB key unlock needs the stick's filesystem UUID; run sudo luxnix-setup-usb-unlock <partition>.";
          }
          {
            assertion =
              builtins.match "[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*" usb.keyPath != null
              && !(lib.any (part: part == ".." || part == ".") (lib.splitString "/" usb.keyPath));
            message = "The USB key path must be a plain relative path on the stick.";
          }
        ];
        boot.initrd = {
          supportedFilesystems = [ usb.fsType ];
          availableKernelModules = [
            "usb_storage"
            "uas"
            "sd_mod"
            "xhci_pci"
          ];
          luks.devices.cryptroot = {
            keyFile = usbKeyFile;
            keyFileTimeout = usb.timeoutSeconds;
          };
        };
      })
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
            # The option type already rejects malformed or overly broad networks.
            assertion = remote.allowedSources != [ ];
            message = ''
              Remote unlock requires at least one management client network. Add a
              trusted host with ip-local in this host's network-cluster to
              luxnix.networkAccess.operatorHosts or leaderHosts, or set
              luxnix.networkAccess.extraEarlyBootSources.
            '';
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
        # Without the identity the initrd cannot be assembled; say how to create it.
        system.preSwitchChecks.remoteUnlockIdentity = ''
          if [ ! -s ${lib.escapeShellArg remote.hostKey} ]; then
            echo 'Remote unlock is enabled, but its early-boot SSH host identity is missing.' >&2
            echo 'Run: sudo luxnix-setup-remote-unlock, pin the printed key, then repeat.' >&2
            exit 1
          fi
        '';
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
