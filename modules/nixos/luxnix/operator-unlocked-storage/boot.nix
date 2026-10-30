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
  enabled = cfg.enable && cfg.layout == "boot-luks";
  mountUnit = path: "${utils.escapeSystemdPath path}.mount";
  luks = lib.concatLists (
    lib.mapAttrsToList (
      _: disk:
      lib.mapAttrsToList (_: p: p.content) (
        lib.filterAttrs (_: p: p.content != null && p.content.type == "luks") disk.content.partitions
      )
    ) (lib.attrByPath [ "disko" "devices" "disk" ] { } config)
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
  dataMounts = lib.unique (
    lib.concatMap (
      v:
      lib.optional (v.content != null && (v.content.mountpoint or null) != null) v.content.mountpoint
      ++ map (s: s.mountpoint) (
        builtins.attrValues (if v.content == null then { } else v.content.subvolumes or { })
      )
    ) secondary
  );
  allMounts = lib.unique (mountsFor paths ++ dataMounts);
  spec = pkgs.writeText "boot-storage.json" (
    builtins.toJSON {
      mounts = lib.genAttrs allMounts (p: {
        inherit (config.fileSystems.${p}) device fsType;
        subvolume = lib.findFirst (o: lib.hasPrefix "subvol=" o) null config.fileSystems.${p}.options;
      });
      keys = map keyFile secondary;
      inherit paths;
      retiredMounts = builtins.filter (p: !(builtins.hasAttr p config.fileSystems)) (
        builtins.attrNames cfg.bindMounts ++ map (v: v.mountPoint) (builtins.attrValues cfg.volumes)
      );
    }
  );
  checker = pkgs.runCommand "boot-storage-checker" { } ''
    mkdir -p "$out"
    cp ${../../../../lx_administration/storage/boot.py} "$out/boot.py"
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
  check = name: "luxnix-storage-check-${name}";
  guard =
    requiredPaths:
    let
      mounts = lib.unique (allMounts ++ mountsFor requiredPaths);
    in
    {
      requires = map mountUnit mounts;
      after = map mountUnit mounts;
      bindsTo = map mountUnit mounts;
      unitConfig.RequiresMountsFor = requiredPaths;
    };
in
{
  config = lib.mkIf enabled {
    assertions = [
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
    ];
    luxnix = lib.optionalAttrs (options.luxnix ? vault) {
      vault.server.managedTls.encryptedStorage = lib.mkForce false;
    };
    boot.initrd.systemd.enable = true;
    boot.initrd.luks.devices.cryptroot.crypttabExtraOpts = [
      "timeout=90s"
      "tries=3"
    ];
    # systemd's stage-2 generator reads these keys only after encrypted root opens.
    environment.etc.crypttab.text =
      lib.concatMapStringsSep "\n" (
        v: "${v.name} ${v.device} ${keyFile v} luks,nofail,headless,x-systemd.device-timeout=30s"
      ) secondary
      + "\n";
    environment.systemPackages = [ verifier ];
    system.preSwitchChecks.encryptedStorage = ''
      ${lib.getExe verifier}
    '';
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
            serviceConfig = {
              Type = "oneshot";
              TimeoutStartSec = "45s";
              ExecStart = "${lib.getExe verifier} ${lib.escapeShellArgs requiredPaths}";
            };
          }
        )
      ) cfg.guardedServices)
    ];
    # Data failures do not hide the console behind an unbounded graphical wait.
    fileSystems = lib.genAttrs dataMounts (_: {
      options = [
        "nofail"
        "x-systemd.device-timeout=30s"
      ]
      ++ map (
        v: "x-systemd.requires=systemd-cryptsetup@${utils.escapeSystemdPath v.name}.service"
      ) secondary;
    });
    systemd.sleep.settings.Sleep = {
      AllowHibernation = false;
      AllowHybridSleep = false;
      AllowSuspendThenHibernate = false;
    };
  };
}
