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

in
{
  options.roles.endoreg-client =
    let
      pathOptions = import ./paths.nix { inherit lib config; };
      apiOptions = import ./api.nix { inherit lib; };
      databaseOptions = import ./database.nix { inherit lib; };
      serviceOptions = import ./service.nix { inherit lib; };
      repositoryOptions = import ./repository.nix { inherit lib; };
      environmentDefaultsOptions = import ./environment-details.nix { inherit lib; };
      lxAnnotateOptions = import ./lx-annotate.nix { inherit lib; };
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

      dbApiLocal = mkOption {
        type = types.bool;
        default = false;
        description = "Deprecated no-op. The endoreg-client role no longer manages a local endo-api service.";
      };

      endoAi = mkOption {
        type = types.bool;
        default = false;
        description = "Enable endoAi service";
      };

      lxAi = mkOption {
        type = types.bool;
        default = false;
        description = "Enable the lx-ai training service unit.";
      };

      defaultCenter = mkOption {
        type = types.str;
        default = "University Hospital Wuerzburg";
        description = "Default center reference for endoreg client. lx-annotate resolves this first as center_key, then as center name.";
        example = "University Hospital Wuerzburg";
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

      # Service Configuration Options
      service = serviceOptions;

      # Git Repository Options
      repository = repositoryOptions;

      environmentDefaults = environmentDefaultsOptions;

      lxAnnotate = lxAnnotateOptions;
    };

  config = mkIf cfg.enable (
    let
      adminUserName =
        if config ? user && config.user ? admin && config.user.admin ? name then
          config.user.admin.name
        else
          "admin";
      adminUid = config.users.users.${adminUserName}.uid or 1000;
      configurationPath =
        if
          config ? luxnix
          && config.luxnix ? "generic-settings"
          && config.luxnix."generic-settings" ? configurationPath
        then
          config.luxnix."generic-settings".configurationPath
        else
          "/home/${adminUserName}/luxnix";
      clientUserName =
        if config ? user && config.user ? client && config.user.client ? name then
          config.user.client.name
        else
          "client-user";
      clientUserHome =
        let
          maybeHome =
            if config ? user && config.user ? client && config.user.client ? home then
              config.user.client.home
            else
              null;
        in
        if maybeHome != null then maybeHome else "/home/${clientUserName}";
      clientHomeStateVersion =
        if config ? user && config.user ? client && config.user.client ? homeStateVersion then
          config.user.client.homeStateVersion
        else
          (config.system.stateVersion or "24.05");
      storageBaseDir = cfg.paths.storageBaseDir;
      videoInputDir = cfg.paths.videoInputDir;
      pdfInputDir = cfg.paths.pdfInputDir;
      desktopDirName = cfg.paths.desktopDirName;
      processingRepo = cfg.paths.processingRepo;
      storagePersistingMountPoint = cfg.paths.storagePersistingMountPoint;

      normalUsers = lib.filterAttrs (_: user: (user.isNormalUser or false)) config.users.users;
      normalUserNames = lib.attrNames normalUsers;

      firstNonNull = values: lib.foldl' (acc: val: if acc != null then acc else val) null values;
      services.nginx.enable = lib.mkForce true;

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

      envDefaultsCfg = cfg.environmentDefaults;
      envOverrides = cfg.lxAnnotate.runtime.environment;

      defaultHfHome = "${endoregServiceUserHome}/.cache/huggingface";
      defaultHfHubCache = "${endoregServiceUserHome}/.cache/huggingface/hub";
      defaultTransformersCache = defaultHfHubCache;
      defaultOllamaModelsDir = "${endoregServiceUserHome}/.ollama/models";

      resolvedHfHome = firstNonNull [
        envOverrides.hfHome
        envDefaultsCfg.hfHome
        defaultHfHome
      ];
      resolvedHfHubCache = firstNonNull [
        envOverrides.hfHubCache
        envDefaultsCfg.hfHubCache
        defaultHfHubCache
      ];
      resolvedTransformersCache = firstNonNull [
        envOverrides.transformersCache
        envDefaultsCfg.transformersCache
        defaultTransformersCache
      ];
      resolvedOllamaModelsDir = firstNonNull [
        envOverrides.ollamaModelsDir
        envDefaultsCfg.ollamaModelsDir
        defaultOllamaModelsDir
      ];
      resolvedOllamaKeepAlive = firstNonNull [
        envOverrides.ollamaKeepAlive
        envDefaultsCfg.ollamaKeepAlive
      ];
      resolvedHfHubEnableTransfer =
        let
          specific = envOverrides.hfHubEnableTransfer;
        in
        if specific != null then specific else envDefaultsCfg.hfHubEnableTransfer;

      annotateEnvironment = {
        hfHome = resolvedHfHome;
        hfHubCache = resolvedHfHubCache;
        transformersCache = resolvedTransformersCache;
        hfHubEnableTransfer = resolvedHfHubEnableTransfer;
        ollamaModelsDir = resolvedOllamaModelsDir;
        ollamaKeepAlive = resolvedOllamaKeepAlive;
      };

      annotateDjangoOverrides = {
        djangoModule = cfg.lxAnnotate.django.djangoModule;
        assetDir =
          if cfg.lxAnnotate.django.assetDir != null then cfg.lxAnnotate.django.assetDir else cfg.api.assetDir;
        port = mkForce 8117;
        djangoAllowedHosts = lib.unique (cfg.api.djangoAllowedHosts ++ [ "lx-annotate.local" ]);
        keycloakClientId = "endoregdb-api";
      };

      annotateExtraSettings =
        let
          baseExtraSettings = cfg.api.extraSettings;
        in
        recursiveUpdate baseExtraSettings (
          {
            CENTRAL_NODES = cfg.centralNodes;
            IS_CENTRAL_NODE = false;
            DEFAULT_CENTER = cfg.defaultCenter;
          }
          // lib.optionalAttrs (cfg.defaultCenterKey != null) {
            DEFAULT_CENTER_KEY = cfg.defaultCenterKey;
          }
        );

      annotateDjango = recursiveUpdate cfg.api (
        annotateDjangoOverrides
        // {
          extraSettings = annotateExtraSettings;
        }
      );
    in
    {
      # Storage settings
      luxnix.storage.enable = mkDefault true;
      services.luxnix.fileMover.enable = mkDefault cfg.lxAnnotate.enable;

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

      luxnix.nvidia-prime.enable = true;

      services.luxnix.endoregDbApiLocal.enable = mkIf (!config.roles.endoreg-db-central-01.enable) (
        mkForce false
      );

      services.luxnix.lxAnnotateLocal = {
        enable = cfg.lxAnnotate.enable;
        debug.enable = cfg.lxAnnotate.debug.enable;
        source = cfg.lxAnnotate.source;
        django = annotateDjango;
        database = cfg.database;
        runtime = {
          commands = mkDefault cfg.lxAnnotate.runtime.commands;
          limits = mkDefault cfg.lxAnnotate.runtime.limits;
          workerLimits = mkDefault cfg.lxAnnotate.runtime.workerLimits;
          workerPools = mkDefault cfg.lxAnnotate.runtime.workerPools;
          frameExtractionWorker = mkDefault cfg.lxAnnotate.runtime.frameExtractionWorker;
          inferenceWorker = mkDefault cfg.lxAnnotate.runtime.inferenceWorker;
          trainingWorker = mkDefault cfg.lxAnnotate.runtime.trainingWorker;
          modelTrainingStagingRoot = mkDefault cfg.lxAnnotate.runtime.modelTrainingStagingRoot;
          externalServices = mkDefault cfg.lxAnnotate.runtime.externalServices;
          celeryBroker = {
            requireSecureTransport = mkIf cfg.lxAnnotate.runtime.celeryBroker.requireSecureTransport (
              mkDefault true
            );
            secureTransportConfirmed = mkIf cfg.lxAnnotate.runtime.celeryBroker.secureTransportConfirmed (
              mkDefault true
            );
          };
          clustered = mkDefault cfg.lxAnnotate.runtime.clustered;
        };
      };

      services.luxnix.lxAiLocal = {
        enable = cfg.lxAi;
        database = cfg.database;
        # optional future improvements
        # source = cfg.repository (if needed)
        # debug.enable = false
        source.branch = "prototype";
        runtime.backboneCheckpointUrl = "https://drive.google.com/uc?export=download&id=1TvliEJ5JTQddIE3kNiGMQzWIe9Cq_7mx";
      };

      services.luxnix.endoAi = {
        enable = false;
      };

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

      security.sudo.extraRules = [
        {
          users = [ adminUserName ];
          commands = [
            {
              command = "${pkgs.util-linux}/bin/mount";
              options = [ "NOPASSWD" ];
            }
            {
              command = "${pkgs.util-linux}/bin/umount";
              options = [ "NOPASSWD" ];
            }
          ];
        }
      ];

      # Periodically ensure the external persisting drive is mounted
      systemd.services.endoreg-mount-persisting-storage =
        mkIf (cfg.paths.storagePersistingEnable && cfg.paths.storagePersistingIsExternalDrive)
          {
            description = "Mount endoreg persisting storage via devenv";
            serviceConfig = {
              Type = "oneshot";
              User = "root";
              Environment = [
                "STORAGE_PERSISTING_EXTERNAL_DRIVE=${
                  if cfg.paths.storagePersistingIsExternalDrive then "true" else "false"
                }"
                "STORAGE_PERSISTING_MOUNT_POINT=${toString storagePersistingMountPoint}"
                "STORAGE_PERSISTING_HDD_ID=${
                  lib.attrByPath [ "secretspec" "secrets" "STORAGE_PERSISTING_HDD_ID" ] "" config
                }"
                "STORAGE_PERSISTING_HDD_PART=${
                  lib.attrByPath [ "secretspec" "secrets" "STORAGE_PERSISTING_HDD_PART" ] "part1" config
                }"
              ];
              ExecStartPre = [ ];
              ExecStart = pkgs.writeShellScript "mount-persisting-storage-service" ''
                set -euo pipefail

                storage_persisting_external_drive="''${STORAGE_PERSISTING_EXTERNAL_DRIVE:-false}"
                storage_persisting_mount_point="''${STORAGE_PERSISTING_MOUNT_POINT:-}"
                storage_persisting_hdd_id="''${STORAGE_PERSISTING_HDD_ID:-}"
                storage_persisting_hdd_part="''${STORAGE_PERSISTING_HDD_PART:-part1}"

                # if STORAGE_PERSISTING_EXTERNAL_DRIVE is not true, exit
                if [ "$storage_persisting_external_drive" != "true" ]; then
                  echo "STORAGE_PERSISTING_EXTERNAL_DRIVE is not true; skipping mount"
                  exit 0

                fi

                if [ -z "$storage_persisting_mount_point" ]; then
                  echo "ERROR: STORAGE_PERSISTING_MOUNT_POINT is not set"
                  exit 1
                fi

                if [ -z "$storage_persisting_hdd_id" ]; then
                  echo "ERROR: STORAGE_PERSISTING_HDD_ID is not set"
                  exit 1
                fi

                # Check if already mounted
                if mountpoint -q "$storage_persisting_mount_point"; then
                  echo "Persisting storage already mounted at $storage_persisting_mount_point"
                  exit 0

                fi

                # attempt to mount drive by ID; prefer first partition if present
                DEV_BASE="/dev/disk/by-id/$storage_persisting_hdd_id"
                DEV_PATH="$DEV_BASE-$storage_persisting_hdd_part"


                echo "Mounting persisting storage drive $DEV_PATH to $storage_persisting_mount_point"
                if [ ! -e "$DEV_PATH" ]; then
                  echo "ERROR: Device path $DEV_PATH does not exist"
                  exit 1
                fi

                mount "$DEV_PATH" "$storage_persisting_mount_point"
                echo "Mounted persisting storage successfully" 

              '';
            };
            path = [
              pkgs.coreutils
              pkgs.util-linux
            ];
          };

      systemd.timers.endoreg-mount-persisting-storage =
        mkIf (cfg.paths.storagePersistingEnable && cfg.paths.storagePersistingIsExternalDrive)
          {
            description = "Periodic mount check for endoreg persisting storage";
            wantedBy = [ "timers.target" ];
            timerConfig = {
              OnBootSec = "1m";
              OnUnitActiveSec = "5m";
              Unit = "endoreg-mount-persisting-storage.service";
            };
          };

      # Update Home Manager configuration to use XDG User Dirs and OutOfStore symlinks
      home-manager.users.${clientUserName} =
        { ... }:
        {
          home.username = mkDefault clientUserName;
          home.stateVersion = mkDefault clientHomeStateVersion;

          roles.desktop.enable = mkDefault true;
        };
    }
  );
}
