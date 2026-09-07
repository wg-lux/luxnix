{
  lib,
  config,
  pkgs,
  ...
}:

with lib;
with lib.luxnix;
let
  cfg = config.roles.endoreg-client;

  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
  endoregServiceGroupName = config.luxnix.generic-settings.endoregServiceGroupName;
  fileMoverDefinition = import ./file-mover.nix { inherit lib; };
  lxAiDefinition = import ./lx-ai.nix { };
  persistingStorageDefinition = import ./persisting-storage.nix { inherit lib; };
  lxAnnotateDefinition = import ./lx-annotate.nix { inherit lib; };

in
{
  options.roles.endoreg-client =
    let
      pathOptions = import ./paths.nix { inherit lib config; };
      apiOptions = import ./api.nix { inherit lib; };
      databaseOptions = import ./database.nix { inherit lib; };
      environmentDefaultsOptions = import ./environment-details.nix { inherit lib; };
    in
    {
      enable = mkEnableOption "Enable endoreg client configuration";
      adminIsServiceUser = mkBoolOpt true "Whether the admin user is also the endoreg service user.";
      paths = pathOptions;

      # Central Nodes Configuration
      centralNodes = mkOption {
        type = types.listOf types.str;
        default = [ ];
        description = "List of hostnames that act as central nodes for the endoreg database API";
        example = [
          "s-04.local"
          "backup-central.local"
        ];
      };

      lxAi = mkOption {
        type = types.bool;
        default = false;
        description = "Enable the lx-ai training service unit.";
      };

      defaultCenterKey = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Optional explicit center_key exported to lx-annotate as DEFAULT_CENTER_KEY. Set this to avoid center-name ambiguity.";
        example = "university_hospital_wuerzburg";
      };

      # Django API Configuration Options
      api = apiOptions;

      # Database Configuration Options
      database = databaseOptions;

      environmentDefaults = environmentDefaultsOptions;

      lxAnnotate = lxAnnotateDefinition.options;
    };

  config = mkIf cfg.enable (
    let
      adminUserName =
        if config ? user && config.user ? admin && config.user.admin ? name then
          config.user.admin.name
        else
          "admin";
      clientUserName =
        if config ? user && config.user ? client && config.user.client ? name then
          config.user.client.name
        else
          "client-user";
      clientHomeStateVersion =
        if config ? user && config.user ? client && config.user.client ? homeStateVersion then
          config.user.client.homeStateVersion
        else
          (config.system.stateVersion or "24.05");
      storageBaseDir = cfg.paths.storageBaseDir;
      videoInputDir = cfg.paths.videoInputDir;
      pdfInputDir = cfg.paths.pdfInputDir;
      storagePersistingMountPoint = cfg.paths.storagePersistingMountPoint;

      normalUsers = lib.filterAttrs (_: user: (user.isNormalUser or false)) config.users.users;
      normalUserNames = lib.attrNames normalUsers;

      firstNonNull = values: lib.foldl' (acc: val: if acc != null then acc else val) null values;
      endoregServiceUserName =
        if
          config ? user && config.user ? endoreg-service-user && config.user.endoreg-service-user ? name
        then
          config.user.endoreg-service-user.name
        else
          "endoreg-service-user";
      endoregServiceUserHome =
        let
          maybeHome =
            if
              config ? user && config.user ? endoreg-service-user && config.user.endoreg-service-user ? home
            then
              config.user.endoreg-service-user.home
            else
              null;
        in
        if maybeHome != null then maybeHome else "/var/${endoregServiceUserName}";

      lxAnnotateRole = lxAnnotateDefinition.entrypoint {
        inherit cfg endoregServiceUserHome firstNonNull;
      };
      fileMoverRole = fileMoverDefinition.entrypoint {
        inherit lxAnnotateRole;
      };
      lxAiRole = lxAiDefinition.entrypoint {
        inherit cfg;
      };
      persistingStorageRole = persistingStorageDefinition.entrypoint {
        inherit
          cfg
          config
          pkgs
          adminUserName
          storagePersistingMountPoint
          ;
      };
    in
    mkMerge [
      {
        luxnix = {
          # Storage settings
          storage.enable = mkDefault true;
          nvidia-prime.enable = true;

          # Development clients must remain usable while the central Vault host is
          # being rebuilt. Existing local secrets are reused; first provisioning
          # still fails closed if a required secret has never been deployed.
          vault.client.allowOffline = mkDefault true;
        };

        user.client.enable = mkDefault true;
        user.endoreg-service-user.enable = true;
        group.endoreg-service.enable = true; # Ensure the group is created
        group.endoreg-service.members = mkAfter (lib.unique normalUserNames);

        roles = {
          desktop.enable = true;
          custom-packages.cuda = true;
          aglnet.client.enable = true;
          managed-secrets.enable = mkDefault true;
        };

        services.luxnix.lxAnnotateLocal = lxAnnotateRole.service;

        services.lx-annotate.extraEnv = mkIf lxAnnotateRole.enable (
          mkDefault lxAnnotateRole.environment.extraEnv
        );

        # Create additional systemd tmpfiles for configuration
        systemd.tmpfiles.rules = [
          # USB Encrypter
          "d /mnt/endoreg-sensitive-data 0770 root ${sensitiveServiceGroupName} -"
          # Service user config directory
          "d /var/endoreg-service-user/config 0755 endoreg-service-user ${endoregServiceGroupName} -"
          # Storage directories (must exist for the symlinks to valid targets)
          "d ${storageBaseDir} 0770 root ${endoregServiceGroupName} -"
          "d ${videoInputDir} 0770 root ${endoregServiceGroupName} -"
          "d ${pdfInputDir} 0770 root ${endoregServiceGroupName} -"
        ]
        ++ lib.optionals cfg.paths.storagePersistingEnable [
          # Persistent storage mount point
          "d ${storagePersistingMountPoint} 0770 root ${endoregServiceGroupName} -"
        ];

        # Update Home Manager configuration to use XDG User Dirs and OutOfStore symlinks
        home-manager.users.${clientUserName} = _: {
          home.username = mkDefault clientUserName;
          home.stateVersion = mkDefault clientHomeStateVersion;

          roles.desktop.enable = mkDefault true;
        };
      }
      fileMoverRole.config
      lxAiRole.config
      persistingStorageRole.config
    ]
  );
}
