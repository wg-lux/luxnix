# Keep backing roots private; services use their declared bind mounts instead.
{
  config,
  lib,
  pkgs,
  utils ? config._module.args.utils,
  ...
}:
let
  storage = config.luxnix.storage.operatorUnlocked;
  permissions = name: "luxnix-storage-permissions-${name}";
  mountUnit = path: "${utils.escapeSystemdPath path}.mount";
in
{
  config = lib.mkIf storage.enable {
    # Do not put these paths in global tmpfiles: that can pull locked mounts
    # into sysinit. Prepare the empty roots independently of mount activation.
    system.activationScripts.luxnixPrivateStorageRoots = {
      deps = [ "specialfs" ];
      text = lib.concatMapStringsSep "\n" (v: ''
        test ! -L ${lib.escapeShellArg v.mountPoint} || exit 1
        ${pkgs.coreutils}/bin/mkdir -p ${lib.escapeShellArg v.mountPoint}
        ${pkgs.coreutils}/bin/chown root:root ${lib.escapeShellArg v.mountPoint}
        ${pkgs.coreutils}/bin/chmod 0700 ${lib.escapeShellArg v.mountPoint}
      '') (builtins.attrValues storage.volumes);
    };
    fileSystems = lib.mkMerge [
      (lib.mapAttrs' (
        _: v:
        lib.nameValuePair v.mountPoint {
          options = [ "x-gvfs-hide" ];
        }
      ) storage.volumes)
      (lib.mapAttrs (_: bind: {
        options = [ "x-systemd.requires=${permissions bind.volume}.service" ];
      }) storage.bindMounts)
    ];
    systemd.services = lib.mkMerge [
      (lib.mapAttrs' (
        name: volume:
        lib.nameValuePair (permissions name) {
          description = "Restrict the ${name} backing root to sudo/root";
          bindsTo = [ (mountUnit volume.mountPoint) ];
          after = [ (mountUnit volume.mountPoint) ];
          before = map mountUnit (
            builtins.attrNames (lib.filterAttrs (_: b: b.volume == name) storage.bindMounts)
          );
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
            UMask = "0077";
          };
          script = ''
            ${pkgs.util-linux}/bin/mountpoint -q ${lib.escapeShellArg volume.mountPoint}
            ${pkgs.coreutils}/bin/chown root:root ${lib.escapeShellArg volume.mountPoint}
            ${pkgs.coreutils}/bin/chmod 0700 ${lib.escapeShellArg volume.mountPoint}
            ${lib.optionalString (volume.container != null) ''
              test ! -L ${lib.escapeShellArg volume.container}
              ${pkgs.coreutils}/bin/chown root:root ${lib.escapeShellArg volume.container}
              ${pkgs.coreutils}/bin/chmod 0600 ${lib.escapeShellArg volume.container}
            ''}
          '';
        }
      ) storage.volumes)
      (lib.mapAttrs (
        _: paths:
        let
          volumes = lib.unique (
            lib.concatMap (
              path:
              if builtins.hasAttr path storage.bindMounts then
                [ storage.bindMounts.${path}.volume ]
              else
                builtins.attrNames (lib.filterAttrs (_: v: v.mountPoint == path) storage.volumes)
            ) paths
          );
          units = map (name: "${permissions name}.service") volumes;
        in
        {
          requires = units;
          after = units;
        }
      ) storage.guardedServices)
    ];
  };
}
