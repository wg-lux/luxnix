{
  config,
  lib,
  pkgs,
  # Snowfall does not forward lazily supplied module arguments.
  utils ? config._module.args.utils,
  ...
}:
let
  cfg = config.luxnix.storage.operatorUnlocked;
  inherit (utils) escapeSystemdPath;
  cleanParts =
    path:
    lib.all (
      part:
      !builtins.elem part [
        ""
        "."
        ".."
      ]
    ) (lib.splitString "/" path);
  absolutePath = lib.types.addCheck (lib.types.strMatching "/[A-Za-z0-9._+@/-]+") (
    path: cleanParts (lib.removePrefix "/" path)
  );
  relativePath = lib.types.addCheck (lib.types.strMatching "[A-Za-z0-9._+@/-]+") cleanParts;
  mountPaths =
    map (v: v.mountPoint) (builtins.attrValues cfg.volumes) ++ builtins.attrNames cfg.bindMounts;
  knownVolumes = lib.all (bind: builtins.hasAttr bind.volume cfg.volumes) (
    builtins.attrValues cfg.bindMounts
  );
  parents = target: builtins.filter (path: lib.hasPrefix "${path}/" target) mountPaths;
  services = lib.mapAttrs (
    _: paths:
    lib.unique (
      paths ++ builtins.filter (path: lib.any (parent: lib.hasPrefix "${parent}/" path) paths) mountPaths
    )
  ) cfg.guardedServices;
  guard = paths: {
    bindsTo = map (path: "${escapeSystemdPath path}.mount") paths;
    unitConfig.RequiresMountsFor = paths;
    unitConfig.AssertPathIsMountPoint = paths;
  };
  migrationConfig = pkgs.writeText "operator-storage-migration.json" (
    builtins.toJSON {
      inherit (cfg) volumes;
      binds = cfg.bindMounts;
      writers = builtins.attrNames cfg.guardedServices;
      accounts = cfg.migration.accountHashes;
      verifier = ../../../../lx_administration/secret_storage.py;
    }
  );
  migrationCommand = "${pkgs.python3}/bin/python ${../../../../lx_administration/storage/operator_migration.py} ${migrationConfig}";
  migrationPath = [
    pkgs.coreutils
    pkgs.cryptsetup
    pkgs.e2fsprogs
    pkgs.rsync
    pkgs.systemd
    pkgs.util-linux
  ];
  unlockName = name: "luxnix-storage-unlock-${name}";
  checkName = name: "luxnix-storage-check-${name}";
  volumeMounts = lib.mapAttrs' (
    name: volume:
    lib.nameValuePair volume.mountPoint {
      inherit (volume) device fsType;
      depends = lib.unique (volume.depends ++ parents volume.mountPoint);
      options = [
        "noauto"
        "nodev"
        "nosuid"
        "x-systemd.device-timeout=${
          if cfg.migration.enable && volume.container != null then "infinity" else "10s"
        }"
      ]
      ++ lib.optional volume.noexec "noexec"
      ++ lib.optionals (cfg.migration.enable && volume.container != null) [
        "x-systemd.requires=${unlockName name}.service"
        "x-systemd.after=${unlockName name}.service"
      ];
    }
  ) cfg.volumes;
  bindMounts = lib.mapAttrs (
    target: bind:
    let
      volume =
        cfg.volumes.${bind.volume} or (throw "Unknown operator-unlocked storage volume: ${bind.volume}");
    in
    {
      device = "${volume.mountPoint}/${bind.directory}";
      fsType = "none";
      options = [
        "bind"
        "noauto"
        "nodev"
        "nosuid"
      ]
      ++ lib.optional volume.noexec "noexec"
      ++ lib.optionals cfg.migration.enable [
        "x-systemd.requires=luxnix-storage-migrate.service"
        "x-systemd.after=luxnix-storage-migrate.service"
      ];
      depends = lib.unique ([ volume.mountPoint ] ++ parents target);
    }
  ) cfg.bindMounts;
in
{
  options.luxnix.storage.operatorUnlocked = {
    enable = lib.mkEnableOption "manually unlocked encrypted storage and guarded consumers";
    migration = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Provision new container files at private passphrase prompts and copy/verify existing data before startup; never format existing storage or delete sources.";
      };
      accountHashes = lib.mkOption {
        type = lib.types.attrsOf absolutePath;
        default = { };
        description = "Boot-available account hash destination mapped to its existing hash source; provisioned once before account validation.";
      };
    };
    volumes = lib.mkOption {
      default = { };
      description = "Encrypted mappings; startup can provision new container files and migrate existing data.";
      type = lib.types.attrsOf (
        lib.types.submodule (
          { name, ... }: {
            options = {
              container = lib.mkOption {
                type = lib.types.nullOr absolutePath;
                default = null;
                description = "Operator-passphrase LUKS container file; null uses an externally unlocked mapping.";
              };
              minimumSizeMiB = lib.mkOption {
                type = lib.types.ints.positive;
                default = 8192;
                description = "Minimum size of a new container; existing source size adds headroom. Existing containers are never resized or reformatted.";
              };
              device = lib.mkOption {
                type = lib.types.strMatching "/dev/mapper/[A-Za-z0-9._+-]+";
                default = "/dev/mapper/${name}";
                description = "Existing dm-crypt mapping, verified before guarded consumers start.";
              };
              mountPoint = lib.mkOption {
                type = absolutePath;
                description = "Private volume mount point.";
              };
              fsType = lib.mkOption {
                type = lib.types.enum [
                  "ext4"
                  "btrfs"
                  "xfs"
                ];
                default = "ext4";
                description = "Existing filesystem type.";
              };
              noexec = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Forbid execution on the volume and its binds.";
              };
              depends = lib.mkOption {
                type = lib.types.listOf absolutePath;
                default = [ ];
                description = "Mounts containing the manually opened backing container.";
              };
            };
          }
        )
      );
    };
    bindMounts = lib.mkOption {
      default = { };
      description = "Destination paths mapped to preserved directories inside a volume; nested targets are ordered automatically.";
      type = lib.types.attrsOf (
        lib.types.submodule {
          options = {
            volume = lib.mkOption {
              type = lib.types.str;
              description = "Name in volumes.";
            };
            directory = lib.mkOption {
              type = relativePath;
              description = "Existing relative directory, without traversal or symlinks.";
            };
          };
        }
      );
    };
    startupServices = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Guarded service basenames started by luxnix-operator-storage start after unlocking.";
    };
    guardedServices = lib.mkOption {
      type = lib.types.attrsOf (lib.types.listOf absolutePath);
      default = { };
      description = "Service names without .service mapped to required mount points; configured nested mounts are included.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion =
          !cfg.migration.enable
          || lib.all (v: v.container == null || v.fsType == "ext4") (builtins.attrValues cfg.volumes);
        message = "Automatic container provisioning supports ext4; use externally prepared mappings for other filesystems.";
      }
      {
        assertion =
          !cfg.migration.enable
          || lib.all (
            v:
            lib.all (target: !(lib.hasPrefix "${target}/" v.mountPoint) && !(builtins.elem target v.depends)) (
              builtins.attrNames cfg.bindMounts
            )
          ) (builtins.attrValues cfg.volumes);
        message = "Migration volume mounts must not depend on destination bind mounts.";
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
        message = "Every operator-unlocked guarded service must define an executable (check for typos or disabled services).";
      }
      {
        assertion = lib.all (name: builtins.hasAttr name cfg.guardedServices) cfg.startupServices;
        message = "Operator-unlocked startupServices must name guarded services.";
      }
      {
        assertion = cfg.volumes != { };
        message = "Operator-unlocked storage requires at least one volume.";
      }
      {
        assertion = builtins.length mountPaths == builtins.length (lib.unique mountPaths);
        message = "Operator-unlocked storage mount points must be unique.";
      }
      {
        assertion = lib.all (path: absolutePath.check path) (builtins.attrNames cfg.bindMounts);
        message = "Operator-unlocked bind targets must be normalized absolute paths.";
      }
      {
        assertion = knownVolumes;
        message = "Operator-unlocked binds must reference configured volumes.";
      }
      {
        assertion =
          !knownVolumes
          || (lib.toposort (
            before: after: builtins.elem before ((volumeMounts // bindMounts).${after}.depends ++ parents after)
          ) mountPaths) ? result;
        message = "Operator-unlocked storage mount dependencies must not contain cycles.";
      }
      {
        assertion = lib.all (name: builtins.match "[A-Za-z0-9@_:-]+" name != null) (
          builtins.attrNames cfg.guardedServices
        );
        message = "Guarded service names must be unit basenames without .service.";
      }
      {
        assertion = lib.all (paths: paths != [ ] && lib.all (path: builtins.elem path mountPaths) paths) (
          builtins.attrValues cfg.guardedServices
        );
        message = "Guarded services require nonempty lists of configured storage mount points.";
      }
    ];
    fileSystems = volumeMounts // bindMounts;
    # Preserve configured encrypted swap. The runtime verifier rejects plaintext
    # partitions/files and zram writeback before any guarded consumer starts.
    system.activationScripts = lib.mkIf (cfg.migration.enable && cfg.migration.accountHashes != { }) {
      luxnixPrepareBootAccountHashes = {
        deps = [ "specialfs" ];
        text = "${migrationCommand} accounts";
      };
      luxnixValidateAdminPasswordFile.deps = [ "luxnixPrepareBootAccountHashes" ];
      luxnixValidateClientPasswordFile.deps = [ "luxnixPrepareBootAccountHashes" ];
    };
    systemd = {
      services =
        lib.mapAttrs (
          name: paths:
          (guard paths)
          // {
            requires = [ "${checkName name}.service" ];
            after = [ "${checkName name}.service" ];
          }
        ) services
        // lib.mapAttrs' (
          name: paths:
          lib.nameValuePair (checkName name) (
            (guard paths)
            // {
              description = "Verify encrypted storage before ${name}";
              # A separate root check also works for consumers with PrivateDevices or User=.
              # RemainAfterExit is deliberately false so a later start checks again.
              path = [ pkgs.util-linux ];
              serviceConfig = {
                Type = "oneshot";
                User = "root";
                UMask = "0077";
                ExecStartPost = "${pkgs.systemd}/bin/systemd-tmpfiles --create ${
                  lib.escapeShellArgs (map (path: "--prefix=${path}") paths)
                }";
                ExecStart = "${pkgs.python3}/bin/python ${../../../../lx_administration/secret_storage.py} ${lib.escapeShellArgs paths}";
              };
            }
          )
        ) services
        // lib.optionalAttrs cfg.migration.enable (
          {
            luxnix-storage-migrate = {
              description = "Migrate and verify data before encrypted bind mounts";
              path = migrationPath;
              unitConfig.DefaultDependencies = false;
              bindsTo = map (v: "${escapeSystemdPath v.mountPoint}.mount") (builtins.attrValues cfg.volumes);
              requires = map (v: "${escapeSystemdPath v.mountPoint}.mount") (builtins.attrValues cfg.volumes);
              after = map (v: "${escapeSystemdPath v.mountPoint}.mount") (builtins.attrValues cfg.volumes);
              serviceConfig = {
                Type = "oneshot";
                RemainAfterExit = true;
                UMask = "0077";
                TimeoutStartSec = "infinity";
                ExecStart = "${migrationCommand} prepare";
              };
            };
          }
          // lib.mapAttrs' (
            name: volume:
            lib.nameValuePair (unlockName name) {
              description = "Unlock operator storage ${name}";
              path = migrationPath;
              unitConfig = {
                DefaultDependencies = false;
                RequiresMountsFor = volume.depends;
              };
              serviceConfig = {
                Type = "oneshot";
                RemainAfterExit = false;
                UMask = "0077";
                TimeoutStartSec = "infinity";
                ExecStart = "${migrationCommand} unlock ${lib.escapeShellArg name}";
              };
            }
          ) (lib.filterAttrs (_: v: v.container != null) cfg.volumes)
        );

      sleep.settings.Sleep = {
        AllowHibernation = false;
        AllowHybridSleep = false;
        AllowSuspendThenHibernate = false;
      };
    };
  };
}
