{
  config,
  lib,
  pkgs,
  utils ? config._module.args.utils,
  ...
}:
let
  cfg = config.luxnix.storage.loginAccess;
  storage = config.luxnix.storage.operatorUnlocked;
  gate = "/run/luxnix-storage-access/unlocked";
  consumers = builtins.attrNames storage.guardedServices;
  mounts =
    map (v: v.mountPoint) (builtins.attrValues storage.volumes)
    ++ builtins.attrNames storage.bindMounts;
  # Reverse the actual mount dependency graph, not path length: /etc/secrets
  # is a bind of /var/lib/luxnix-secrets despite having a shorter name.
  mountOrder =
    (lib.toposort (
      a: b:
      builtins.elem a (
        if builtins.hasAttr b storage.bindMounts then
          [ storage.volumes.${storage.bindMounts.${b}.volume}.mountPoint ]
        else
          lib.concatMap (v: lib.optionals (v.mountPoint == b) v.depends) (builtins.attrValues storage.volumes)
      )
      || lib.hasPrefix "${a}/" b
    ) mounts).result;
  reverseMounts = lib.reverseList mountOrder;
  mountUnit = path: "${utils.escapeSystemdPath path}.mount";
  triggers =
    (map (name: "${name}.timer") (
      builtins.attrNames (
        lib.filterAttrs (
          name: timer:
          timer.enable
          && builtins.elem (lib.removeSuffix ".service" (
            timer.timerConfig.Unit or "${name}.service"
          )) consumers
        ) config.systemd.timers
      )
    ))
    ++ (map (name: "${name}.path") (
      builtins.attrNames (
        lib.filterAttrs (
          name: path:
          path.enable
          && builtins.elem (lib.removeSuffix ".service" (path.pathConfig.Unit or "${name}.service")) consumers
        ) config.systemd.paths
      )
    ));
  settings = pkgs.writeText "storage-login-access.json" (
    builtins.toJSON {
      inherit (cfg) users autoEnroll;
      inherit triggers;
      startupTriggers = builtins.filter (
        unit:
        if lib.hasSuffix ".timer" unit then
          config.systemd.timers.${lib.removeSuffix ".timer" unit}.wantedBy != [ ]
        else
          config.systemd.paths.${lib.removeSuffix ".path" unit}.wantedBy != [ ]
      ) triggers;
      consumers =
        map (name: "${name}.service") consumers
        ++ map (name: "luxnix-storage-unlock-${name}.service") (builtins.attrNames storage.volumes);
      startup = map (name: "${name}.service") storage.startupServices;
      mounts = map mountUnit mountOrder;
      mountsReverse = map mountUnit reverseMounts;
      volumes = builtins.attrValues storage.volumes;
    }
  );
  python = pkgs.runCommand "storage-login-access-python" { } ''
    mkdir -p "$out"
    cp ${../../../../lx_administration/storage/login_access.py} "$out/login_access.py"
    cp ${../../../../lx_administration/storage/openbao_local.py} "$out/openbao_local.py"
    cp ${../../../../lx_administration/secret_storage.py} "$out/secret_storage.py"
  '';
  helper = pkgs.writeShellApplication {
    name = "luxnix-storage-access";
    runtimeInputs = [
      pkgs.systemd
      pkgs.cryptsetup
      pkgs.util-linux
    ];
    text = ''exec ${pkgs.python3}/bin/python ${python}/login_access.py --config ${settings} "$@"'';
  };
  verifySeal = pkgs.writeShellScript "verify-login-seal" ''
    exec ${pkgs.python3}/bin/python -c ${lib.escapeShellArg "import runpy; runpy.run_path('${python}/openbao_local.py')['verify_staged_seal']()"}
  '';
  pam = pkgs.runCommandCC "pam-luxnix-storage" { buildInputs = [ pkgs.pam ]; } ''
    mkdir -p "$out/lib/security"
    $CC -Wall -Wextra -Werror -O2 -fPIC -shared \
      -DHELPER='"${helper}/bin/luxnix-storage-access"' \
      ${./pam_storage_access.c} -lpam -o "$out/lib/security/pam_luxnix_storage.so"
  '';
  pamRule = {
    enable = true;
    control = "optional";
    modulePath = "${pam}/lib/security/pam_luxnix_storage.so";
    args = cfg.users;
  };
in
{
  imports = [ ./private-roots.nix ];

  options.luxnix.storage.loginAccess = {
    enable = lib.mkEnableOption "password-login and remote OpenBao storage access" // {
      default =
        (lib.attrByPath [ "roles" "endoreg-client" "enable" ] false config)
        && storage.unlockMethod == "local-openbao"
        && config.luxnix.openbao.local.seal == "passphrase";
    };
    users = lib.mkOption {
      type = lib.types.listOf (lib.types.strMatching "[a-z_][a-z0-9_-]*");
      default = [
        config.user.admin.name
      ]
      ++ lib.optional config.user.client.enable config.user.client.name;
      description = "Accounts allowed to wrap the existing seal and unlock storage after password authentication.";
    };
    autoEnroll = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Enroll missing account wraps on successful login, only while the canonical seal is already authenticated and staged.";
    };
    pamServices = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "login"
        "sshd"
      ];
      description = "Password PAM stacks (SDDM includes login); key-only SSH and autologin do not carry an unlock password.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion =
          storage.enable
          && storage.unlockMethod == "local-openbao"
          && config.luxnix.openbao.local.enable
          && config.luxnix.openbao.local.seal == "passphrase"
          && storage.startupServices != [ ]
          && cfg.users != [ ];
        message = "Login storage access requires enrolled/adopted passphrase-sealed local OpenBao and guarded startup services.";
      }
    ];
    environment.systemPackages = [ helper ];
    # Login-controlled mounts must not order before local-fs.target. Explicit
    # starts still require successful mounts and the encrypted-storage guards.
    fileSystems = lib.genAttrs mounts (_: {
      options = [ "nofail" ];
    });
    security.pam.services = lib.genAttrs cfg.pamServices (name: {
      rules.auth.luxnix-storage = pamRule // {
        order = config.security.pam.services.${name}.rules.auth.unix.order - 1;
      };
      rules.session.luxnix-storage = pamRule // {
        order = 1;
      };
    });
    systemd.tmpfiles.rules = [ "d /run/luxnix-storage-access 0700 root root -" ];
    systemd.services = lib.mkMerge [
      (lib.genAttrs consumers (_: {
        unitConfig.ConditionPathExists = gate;
      }))
      (lib.mapAttrs' (
        name: _:
        lib.nameValuePair "luxnix-storage-unlock-${name}" {
          unitConfig.ConditionPathExists = gate;
        }
      ) storage.volumes)
      {
        openbao-local = {
          wantedBy = lib.mkForce [ ];
          unitConfig.ConditionPathExists = gate;
        };
        openbao-local-seal-key = {
          before = lib.mkForce [ ];
          unitConfig.ConditionPathExists = gate;
          # PAM/remote helper authenticates the key. Never prompt during boot.
          serviceConfig.ExecStart = lib.mkForce "${verifySeal}";
        };
      }
    ];
  };
}
