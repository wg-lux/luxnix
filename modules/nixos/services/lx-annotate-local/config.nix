args@{ lib, ... }:
with lib;
with lib.luxnix;
with args;
let
  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-user-home
    endoreg-service-group-name
    ;
  inherit (runtime.names) scriptName exportFramesScriptName;
  inherit (runtime.paths)
    runtimeRootPath
    repoDir
    repoStaticRootPath
    runtimeDataRootPath
    runtimeStorageRootPath
    runtimeIoImportRootPath
    runtimeWatcherVideoDirPath
    runtimeWatcherReportDirPath
    runtimeWatcherPreanonymizedDirPath
    runtimeSapImportDirPath
    runtimeMoverStagingDirPath
    runtimeStreamableVideoRootPath
    runtimeStreamableVideoRawRootPath
    runtimeStreamableVideoProcessedRootPath
    runtimeStaticRootPath
    runtimeWheelRootPath
    runtimeWheelVenvPath
    runtimeWorkingDir
    staticRootPath
    djangoStaticRootPath
    envDataDir
    envConfDir
    sslKeyPath
    sslCertPath
    hubRootPath
    ;
  inherit (runtime.runtime)
    useWheelRuntime
    managedEncryptedDataServiceName
    encryptionServiceUnits
    ;
  inherit (runtime.defaults)
    defaultSslCertificatePath
    defaultSslKeyPath
    ;
  inherit (runtime.env)
    envDefaultCenter
    envDeploymentRole
    ;
  inherit (runtime.scripts.scriptNames)
    acceptanceScriptName
    celeryFrameExtractionWorkerScriptName
    celeryFfmpegWorkerScriptName
    celeryInferenceWorkerScriptName
    celeryPipelineWorkerScriptName
    celeryTrainingWorkerScriptName
    celeryWorkerScriptName
    emergencyStorageReliefScriptName
    loadBaseDataWheelScriptName
    masterKeyCheckScriptName
    migrateWheelScriptName
    migrateVideoStreamableStorageScriptName
    watcherScriptName
    sapImportScriptName
    ;
  inherit (runtime.scripts.packages)
    lxAnnotateBootstrapScript
    lxAnnotateEncryptedDataMountScript
    lxAnnotateEncryptedDataUmountScript
    lxAnnotateMigrateVideoStreamableStorageScript
    runLocalAcceptanceScript
    runLocalAcceptanceWheelScript
    runLocalCeleryFrameExtractionWorkerScript
    runLocalCeleryFrameExtractionWorkerWheelScript
    runLocalCeleryFfmpegWorkerScript
    runLocalCeleryFfmpegWorkerWheelScript
    runLocalCeleryInferenceWorkerScript
    runLocalCeleryInferenceWorkerWheelScript
    runLocalCeleryPipelineWorkerScript
    runLocalCeleryPipelineWorkerWheelScript
    runLocalCeleryTrainingWorkerScript
    runLocalCeleryTrainingWorkerWheelScript
    runLocalCeleryWorkerScript
    runLocalCeleryWorkerWheelScript
    runLocalDataCleanupScript
    runLocalDataRecoveryScript
    runLocalEmergencyStorageReliefScript
    runLocalExportFramesScript
    runLocalExportFramesWheelScript
    runLocalFileWatcherScript
    runLocalFileWatcherWheelScript
    runLocalHubBackupScript
    runLocalLoadBaseDataWheelScript
    runLocalLxAnnotateStartScript
    runLocalLxAnnotateWheelScript
    runLocalMasterKeyCheckWheelScript
    runLocalMigrateWheelScript
    runLocalSapImportScript
    runLocalSapImportWheelScript
    ;
  servicePathEnv = "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin";
  nixPathEnv = "NIX_PATH=nixpkgs=${pkgs.path}";
  endoregCentralServer = lib.attrByPath [ "roles" "endoreg-db-central-01" "enable" ] false config;
  deploymentRoleEnv = "ENDOREG_DEPLOYMENT_ROLE=${envDeploymentRole}";
  hubModeEnv = "ENDOREG_HUB_MODE=${if cfg.hub.enable then "true" else "false"}";
  enableHubTransfersEnv = "ENDOREG_ENABLE_HUB_TRANSFERS=${
    if cfg.hub.transferApi.enable then "true" else "false"
  }";
  hubTransferRequireSecureTransportEnv = "ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=${
    if cfg.hub.transferApi.requireSecureTransport then "true" else "false"
  }";
  hubTransferRequireMtlsEnv = "ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=${
    if cfg.hub.transferApi.requireMtls then "true" else "false"
  }";
  hubTransferMtlsMetaKeyEnv = "ENDOREG_HUB_TRANSFER_MTLS_META_KEY=${cfg.hub.transferApi.mtlsMetaKey}";
  hubTransferMtlsMetaValueEnv = "ENDOREG_HUB_TRANSFER_MTLS_META_VALUE=${cfg.hub.transferApi.mtlsMetaValue}";
  defaultCenterEnv = "LX_ANNOTATE_DEFAULT_CENTER=${envDefaultCenter}";
  externalPostgresConfigured = cfg.runtime.externalServices.postgresHost != null;
  externalRedisConfigured = cfg.runtime.externalServices.redisUrl != null;
  celeryBrokerUrl =
    if cfg.runtime.externalServices.redisUrl != null then
      cfg.runtime.externalServices.redisUrl
    else
      lib.attrByPath [
        "roles"
        "endoreg-client"
        "service"
        "extraEnvironment"
        "CELERY_BROKER_URL"
      ] "redis://localhost:6379/1" config;
  localPostgresSetupUnits = lib.optionals (!externalPostgresConfigured) [
    "postgres-endoreg-setup.service"
  ];
  localPostgresServiceUnits = lib.optionals (!externalPostgresConfigured) [ "postgresql.service" ];
  localRedisServiceUnits = lib.optionals (!externalRedisConfigured) [ "redis-lx-annotate.service" ];
  celeryWorkerServiceUnits = [
    "lx-annotate-celery-worker.service"
    "lx-annotate-celery-pipeline-worker.service"
    "lx-annotate-celery-ffmpeg-worker.service"
    "lx-annotate-celery-frame-extraction-worker.service"
    "lx-annotate-celery-inference-worker.service"
    "lx-annotate-celery-training-worker.service"
  ];
  wheelBootstrapUnits = lib.optionals useWheelRuntime [
    "lx-annotate-migrate.service"
    "lx-annotate-load-base-data.service"
  ];
  masterKeyCheckUnits = lib.optionals useWheelRuntime [
    "lx-annotate-master-key-check.service"
  ];
  isLocalPostgresHost =
    host: host == "localhost" || host == "127.0.0.1" || host == "::1" || host == cfg.django.hostname;
  isLocalRedisUrl =
    url:
    url != null
    && (lib.hasInfix "localhost" url || lib.hasInfix "127.0.0.1" url || lib.hasInfix "[::1]" url);
  brokerUrlUsesSecureTransport =
    url: url != null && (lib.hasPrefix "rediss:" url || lib.hasPrefix "amqps:" url);
  wheelRuntimePreStart = "+${pkgs.writeShellScript "lx-annotate-wheel-runtime-pre-start" ''
    set -euo pipefail

    ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${endoreg-service-user-home}
    ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
    ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envDataDir}
    ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeWheelRootPath}
    ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeWheelVenvPath}
    ${pkgs.coreutils}/bin/install -d -m 0775 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeStaticRootPath}
    ${pkgs.coreutils}/bin/install -d -m 0775 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeStaticRootPath}/.vite

    SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
    TARGET_PWD="${envConfDir}/db_pwd"

    if [ -f "$SOURCE_PWD" ]; then
      cp "$SOURCE_PWD" "$TARGET_PWD"
      chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
      chmod 600 "$TARGET_PWD"
    else
      echo "WARNING: Password file $SOURCE_PWD not found!"
    fi

    [ -f "${cfg.django.keycloakSecretFile}" ] && chown root:${endoreg-service-group-name} "${cfg.django.keycloakSecretFile}"
    [ -f "${cfg.django.keycloakSecretFile}" ] && chmod 640 "${cfg.django.keycloakSecretFile}"
  ''}";
  stopWheelCeleryWorkersPreStart = "+${pkgs.writeShellScript "lx-annotate-stop-wheel-celery-workers" ''
    set -euo pipefail

    for unit in ${lib.concatStringsSep " " celeryWorkerServiceUnits}; do
      ${pkgs.systemd}/bin/systemctl stop "$unit" >/dev/null 2>&1 || true
    done
  ''}";
  runtimeLibraryPackages = [
    pkgs.stdenv.cc.cc.lib
    pkgs.libglvnd
    pkgs.zlib
    pkgs.glib
    pkgs.libxcb
  ];
  runtimeLdLibraryPathEnv = "LD_LIBRARY_PATH=${lib.makeLibraryPath runtimeLibraryPackages}";
  runtimeFfmpegLdLibraryPathEnv = "LD_LIBRARY_PATH=${
    lib.makeLibraryPath (runtimeLibraryPackages ++ [ pkgs.ffmpeg ])
  }";
  fileMoverServiceUserHome =
    config.user.endoreg-service-user.extraOptions.home or "/var/${endoreg-service-user-name}";
  fileMoverRepoDir = "${fileMoverServiceUserHome}/lx-annotate";
  fileMoverWheelRootPath = "${fileMoverServiceUserHome}/lx-annotate-wheel";
  fileMoverWheelVenvPath = "${fileMoverWheelRootPath}/.venv";
  fileMoverRuntimeWorkingDir = if useWheelRuntime then fileMoverWheelRootPath else fileMoverRepoDir;
  fileMoverConfDir =
    if useWheelRuntime then
      "${fileMoverWheelRootPath}/${cfg.django.confDir}"
    else
      "${fileMoverRepoDir}/${cfg.django.confDir}";
  serviceUserIoAccessLinkPath = "${fileMoverServiceUserHome}/lx-annotate-io";
  desktopPreanonymizedLinkTarget = "${serviceUserIoAccessLinkPath}/preanonymized_import";
  desktopSapImportLinkTarget = "${serviceUserIoAccessLinkPath}/sap_import";
  lxAnnotateTranscodeVideoCommand =
    if useWheelRuntime then
      if cfg.runtime.commands.transcodeVideo == null then "" else cfg.runtime.commands.transcodeVideo
    else
      "python manage.py transcode_video";
  lxAnnotateFileMoverTranscodeCommand =
    if lxAnnotateTranscodeVideoCommand == "" then
      null
    else
      "${lxAnnotateTranscodeVideoCommand} --input-dir \"$1\" --filename \"$2\" --output-dir \"$3\" --overwrite --json";
  lxAnnotateFileMoverTranscodeEnv = ''
    export LX_ANNOTATE_WHEEL_VENV="${fileMoverWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${fileMoverWheelRootPath}"
    export DJANGO_SETTINGS_MODULE="lx_annotate.settings.settings_prod"
    export DJANGO_SETTINGS_MODULE_PRODUCTION="lx_annotate.settings.settings_prod"
    export DJANGO_ENV="production"
    export DATA_DIR="${runtimeDataRootPath}"
    export LX_ANNOTATE_DATA_DIR="${runtimeDataRootPath}"
    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${runtimeDataRootPath}"
    export PROTECTED_MEDIA_ROOT="${runtimeDataRootPath}/storage"
    export STORAGE_DIR="${runtimeDataRootPath}/storage"
    export WATCHER_VIDEO_DIR="${runtimeWatcherVideoDirPath}"
    export WATCHER_REPORT_DIR="${runtimeWatcherReportDirPath}"
    export WATCHER_PREANONYMIZED_DIR="${runtimeWatcherPreanonymizedDirPath}"
    export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
    export REQUESTS_CA_BUNDLE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"

    export DJANGO_SECRET_KEY_FILE="${toString cfg.django.djangoSecretKeyFile}"
    django_secret_key="$(${pkgs.coreutils}/bin/tr -d '\n' < "${toString cfg.django.djangoSecretKeyFile}" 2>/dev/null || true)"
    export DJANGO_SECRET_KEY="$django_secret_key"

    export CONF_DIR="${fileMoverConfDir}"
    export DB_PWD_FILE="${fileMoverConfDir}/db_pwd"
    export DJANGO_DB_PASSWORD_FILE="${fileMoverConfDir}/db_pwd"
    db_pwd="$(${pkgs.coreutils}/bin/tr -d '\n' < "${fileMoverConfDir}/db_pwd" 2>/dev/null || true)"
    export DJANGO_DB_ENGINE="django.db.backends.postgresql"
    export DJANGO_DB_NAME="${cfg.database.name}"
    export DJANGO_DB_USER="${cfg.database.user}"
    export DJANGO_DB_PASSWORD="$db_pwd"
    export DJANGO_DB_HOST="${cfg.database.host}"
    export DJANGO_DB_PORT="${toString cfg.database.port}"
    export DJANGO_DB_SSLMODE="${cfg.database.sslMode}"

    export DJANGO_ALLOWED_HOSTS="${lib.concatStringsSep "," cfg.django.djangoAllowedHosts}"
    export ALLOWED_HOSTS="${lib.concatStringsSep "," cfg.django.djangoAllowedHosts}"
    export DJANGO_CORS_ALLOWED_ORIGINS="${lib.concatStringsSep "," cfg.django.corsAllowedOrigins}"
    export DJANGO_CSRF_TRUSTED_ORIGINS="${lib.concatStringsSep "," cfg.django.corsAllowedOrigins}"
    export OIDC_RP_CLIENT_ID="${cfg.django.keycloakClientId}"
    oidc_client_secret="$(${pkgs.coreutils}/bin/tr -d '\n' < "${toString cfg.django.keycloakSecretFile}" 2>/dev/null || true)"
    export OIDC_RP_CLIENT_SECRET="$oidc_client_secret"
  '';
  commonServiceEnvironment = [
    servicePathEnv
    nixPathEnv
    deploymentRoleEnv
    hubModeEnv
    enableHubTransfersEnv
    hubTransferRequireSecureTransportEnv
    hubTransferRequireMtlsEnv
    hubTransferMtlsMetaKeyEnv
    hubTransferMtlsMetaValueEnv
    defaultCenterEnv
  ];
  appServiceEnvironment = commonServiceEnvironment ++ [
    runtimeLdLibraryPathEnv
  ];
  celeryWorkerEnvironment = commonServiceEnvironment ++ [
    runtimeFfmpegLdLibraryPathEnv
  ];
  encryptedDataMountUnitConfig = {
    RequiresMountsFor = [ envDataDir ];
  };
  appReadWritePaths = [
    endoreg-service-user-home
    envDataDir
    envConfDir
    staticRootPath
    runtimeRootPath
    runtimeWheelRootPath
    runtimeWheelVenvPath
    cfg.runtime.modelTrainingStagingRoot
    "/var/endoreg-service-user/lx-annotate"
  ];
  celeryWorkerEnabled = !useWheelRuntime || cfg.runtime.commands.celeryWorker != null;
  frameExtractionWorkerMode = cfg.runtime.frameExtractionWorker.mode;
  frameExtractionWorkerBootRequires = lib.optionals (frameExtractionWorkerMode != "always") [
    "lx-annotate-boot.service"
  ];
  frameExtractionWorkerBootWantedBy = lib.optionals (frameExtractionWorkerMode == "always") [
    "lx-annotate-boot.service"
  ];
  ffmpegWorkerMode = cfg.runtime.ffmpegWorker.mode;
  ffmpegWorkerBootWantedBy = lib.optionals (ffmpegWorkerMode == "always") [
    "lx-annotate-boot.service"
  ];
  ffmpegWorkerBootRequires = lib.optionals (ffmpegWorkerMode != "always") [
    "lx-annotate-boot.service"
  ];
  inferenceWorkerMode = cfg.runtime.inferenceWorker.mode;
  inferenceWorkerBootWantedBy = lib.optionals (inferenceWorkerMode == "always") [
    "lx-annotate-boot.service"
  ];
  inferenceWorkerBootRequires = lib.optionals (inferenceWorkerMode != "always") [
    "lx-annotate-boot.service"
  ];
  trainingWorkerMode = cfg.runtime.trainingWorker.mode;
  trainingWorkerBootWantedBy = lib.optionals (trainingWorkerMode == "always") [
    "lx-annotate-boot.service"
  ];
  trainingWorkerBootRequires = lib.optionals (trainingWorkerMode != "always") [
    "lx-annotate-boot.service"
  ];
  mkCeleryWorkerService =
    {
      description,
      execStart,
      memoryHigh,
      memoryMax,
      cpuQuota,
      nice,
      oomScoreAdjust,
      wantedBy ? [ "lx-annotate-boot.service" ],
      partOf ? [ "lx-annotate-boot.service" ],
      wants ? [ ],
      requires ? [ ],
      restart ? "always",
      startupDelaySec ? null,
      runtimeMaxSec ? null,
      timeoutStopSec ? null,
      extraServiceConfig ? { },
    }:
    {
      inherit description wantedBy partOf;
      after =
        localRedisServiceUnits
        ++ localPostgresServiceUnits
        ++ [ "lx-annotate-boot.service" ]
        ++ wheelBootstrapUnits
        ++ encryptionServiceUnits;
      wants = localRedisServiceUnits ++ encryptionServiceUnits ++ wants;
      requires =
        localRedisServiceUnits
        ++ lib.optionals useWheelRuntime [ "lx-annotate-boot.service" ]
        ++ encryptionServiceUnits
        ++ requires;
      unitConfig = encryptedDataMountUnitConfig;

      serviceConfig = {
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = execStart;
        Restart = restart;
        RestartSec = "15s";
        Environment = celeryWorkerEnvironment;
        MemoryHigh = memoryHigh;
        MemoryMax = memoryMax;
        CPUQuota = cpuQuota;
        Nice = nice;
        IOSchedulingClass = "idle";
        OOMScoreAdjust = oomScoreAdjust;
        ReadWritePaths = appReadWritePaths;
      }
      // optionalAttrs (startupDelaySec != null) {
        ExecStartPre = [ "${pkgs.coreutils}/bin/sleep ${startupDelaySec}" ];
      }
      // optionalAttrs (runtimeMaxSec != null) {
        RuntimeMaxSec = runtimeMaxSec;
      }
      // optionalAttrs (timeoutStopSec != null) {
        TimeoutStopSec = timeoutStopSec;
      }
      // extraServiceConfig;
    };
in
{
  config = mkIf cfg.enable {
    services.luxnix.lxAnnotateLocal.hub.enable = mkDefault (
      config.networking.hostName == "gs-02" || endoregCentralServer
    );
    services.luxnix.lxAnnotateLocal.runtime.deploymentRole = mkDefault (
      if cfg.hub.enable || endoregCentralServer then "central_hub" else "site_node"
    );
    services.luxnix.lxAnnotateLocal.runtime.celeryBroker.requireSecureTransport = mkDefault (
      cfg.runtime.clustered.enable
      || (externalRedisConfigured && !isLocalRedisUrl cfg.runtime.externalServices.redisUrl)
    );
    services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = mkIf (
      cfg.runtime.deploymentRole == "central_hub"
    ) (mkDefault true);
    services.luxnix.fileMover = {
      paths = {
        destinationVideoDir = mkDefault runtimeWatcherVideoDirPath;
        destinationReportDir = mkDefault runtimeWatcherReportDirPath;
        stagingDir = mkDefault runtimeMoverStagingDirPath;
      };
      desktop.links = {
        preanonymized_import = mkDefault desktopPreanonymizedLinkTarget;
        sap_import = mkDefault desktopSapImportLinkTarget;
      };
      videoTranscodeFallback = {
        command = mkDefault lxAnnotateFileMoverTranscodeCommand;
        workingDir = mkDefault fileMoverRuntimeWorkingDir;
        environmentScript = mkDefault lxAnnotateFileMoverTranscodeEnv;
      };
    };
    assertions = [
      {
        assertion = cfg.runtime.mode != "wheel" || cfg.runtime.wheelPath != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set when runtime.mode = \"wheel\".";
      }
      {
        assertion = !cfg.runtime.clustered.enable || cfg.runtime.externalServices.redisUrl != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.externalServices.redisUrl.";
      }
      {
        assertion =
          !cfg.runtime.celeryBroker.requireSecureTransport
          || cfg.runtime.celeryBroker.secureTransportConfirmed
          || brokerUrlUsesSecureTransport celeryBrokerUrl;
        message = "services.luxnix.lxAnnotateLocal.runtime.celeryBroker.requireSecureTransport requires a rediss:// or amqps:// broker URL, or runtime.celeryBroker.secureTransportConfirmed = true.";
      }
      {
        assertion = cfg.runtime.deploymentRole != "central_hub" || cfg.hub.enable;
        message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires hub.enable = true. LuxNix servers/central nodes use central_hub; laptop center nodes use site_node.";
      }
      {
        assertion =
          cfg.runtime.deploymentRole != "central_hub" || cfg.hub.transferApi.requireSecureTransport;
        message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires hub.transferApi.requireSecureTransport = true to match lx-annotate production settings.";
      }
      {
        assertion = cfg.runtime.deploymentRole != "central_hub" || cfg.hub.transferApi.requireMtls;
        message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires hub.transferApi.requireMtls = true to match lx-annotate production settings.";
      }
      {
        assertion =
          cfg.runtime.deploymentRole != "central_hub"
          || (cfg.hub.transferApi.mtlsMetaKey != "" && cfg.hub.transferApi.mtlsMetaValue != "");
        message = "services.luxnix.lxAnnotateLocal.runtime.deploymentRole = \"central_hub\" requires non-empty hub.transferApi.mtlsMetaKey and mtlsMetaValue.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || !isLocalRedisUrl cfg.runtime.externalServices.redisUrl;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires a non-local Redis URL.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || cfg.runtime.externalServices.postgresHost != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.externalServices.postgresHost.";
      }
      {
        assertion =
          !cfg.runtime.clustered.enable || !isLocalPostgresHost cfg.runtime.externalServices.postgresHost;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires a non-local PostgreSQL host.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || cfg.runtime.clustered.sharedStorage;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.clustered.sharedStorage = true.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || cfg.runtime.clustered.sharedMasterKeyFile != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.clustered.sharedMasterKeyFile.";
      }
      {
        assertion =
          !cfg.runtime.clustered.enable
          || cfg.runtime.masterKeyFile == cfg.runtime.clustered.sharedMasterKeyFile;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.masterKeyFile to match runtime.clustered.sharedMasterKeyFile.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || !cfg.runtime.autoGenerateMasterKey;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires runtime.autoGenerateMasterKey = false.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || !cfg.runtime.managedEncryptedData.enable;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable does not support per-host managedEncryptedData.";
      }
      {
        assertion = !cfg.runtime.clustered.enable || !cfg.runtime.vaultManagedEncryptedData.enable;
        message = "services.luxnix.lxAnnotateLocal.runtime.clustered.enable requires a shared workload master key, not hostname-scoped vaultManagedEncryptedData.";
      }
      {
        assertion =
          !lib.hasPrefix "${repoDir}/" cfg.runtime.encryptedDataDir
          && cfg.runtime.encryptedDataDir != repoDir
          && !lib.hasPrefix "${runtimeWheelRootPath}/" cfg.runtime.encryptedDataDir
          && cfg.runtime.encryptedDataDir != runtimeWheelRootPath;
        message = "services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir must stay outside the repo/app path.";
      }
      {
        assertion =
          !cfg.runtime.managedEncryptedData.enable
          || cfg.runtime.managedEncryptedData.luksUuid != null
          || cfg.runtime.managedEncryptedData.luksUuidFile != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.luksUuid or luksUuidFile must be set when managedEncryptedData.enable = true.";
      }
      {
        assertion =
          !cfg.runtime.managedEncryptedData.enable || cfg.runtime.managedEncryptedData.keyFile != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.keyFile must be set when managedEncryptedData.enable = true.";
      }
      {
        assertion =
          !cfg.runtime.managedEncryptedData.enable
          || cfg.runtime.encryptionService == null
          || cfg.runtime.encryptionService == managedEncryptedDataServiceName;
        message = "services.luxnix.lxAnnotateLocal.runtime.encryptionService must stay unset or equal to lx-annotate-encrypted-data.service when managedEncryptedData.enable = true.";
      }
      {
        assertion = !cfg.runtime.vaultManagedEncryptedData.enable || config.networking.hostName != "";
        message = "services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData requires networking.hostName to be set.";
      }
      {
        assertion =
          !cfg.runtime.vaultManagedEncryptedData.enable
          || (
            config.luxnix.vault.enable
            && (
              config.luxnix.vault.client.auth.method != "none"
              || config.luxnix.vault.client.environmentFile != null
            )
          );
        message = "services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData requires luxnix.vault client configuration, either via auth bootstrap or a declared environmentFile.";
      }
      {
        assertion =
          cfg.runtime.masterKeyFile != null
          || cfg.runtime.autoGenerateMasterKey
          || (
            cfg.runtime.vaultManagedEncryptedData.enable
            && cfg.runtime.vaultManagedEncryptedData.manageMasterKey
          );
        message = "services.luxnix.lxAnnotateLocal requires an application master key for encrypted storage. Set runtime.masterKeyFile, keep runtime.autoGenerateMasterKey = true, or enable vaultManagedEncryptedData.manageMasterKey.";
      }
      {
        assertion = !cfg.hub.backup.enable || cfg.hub.enable;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.enable requires services.luxnix.lxAnnotateLocal.hub.enable.";
      }
      {
        assertion = !cfg.hub.transferApi.enable || cfg.hub.enable;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.enable.";
      }
      {
        assertion = !cfg.hub.transferApi.enable || cfg.hub.transferApi.requireSecureTransport;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.requireSecureTransport = true.";
      }
      {
        assertion = !cfg.hub.transferApi.enable || cfg.hub.transferApi.requireMtls;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = true.";
      }
      {
        assertion = !cfg.hub.transferApi.enable || cfg.hub.transferApi.clientCaFile != null;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.clientCaFile to be set.";
      }
      {
        assertion =
          !cfg.hub.transferApi.enable
          || (cfg.hub.transferApi.mtlsMetaKey != "" && cfg.hub.transferApi.mtlsMetaValue != "");
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires non-empty mTLS meta key and value.";
      }
      {
        assertion =
          !cfg.hub.backup.enable
          || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.incomingDir;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.incomingDir must stay inside runtime.encryptedDataDir.";
      }
      {
        assertion =
          !cfg.hub.backup.enable
          || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.snapshotDir;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.snapshotDir must stay inside runtime.encryptedDataDir.";
      }
      {
        assertion =
          !cfg.hub.backup.enable
          || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.manifestDir;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.manifestDir must stay inside runtime.encryptedDataDir.";
      }
      {
        assertion =
          !cfg.storageRelief.enable
          || !cfg.storageRelief.requireExternalMount
          || cfg.storageRelief.expectedDeviceId != null
          || cfg.storageRelief.expectedFsUuid != null;
        message = "services.luxnix.lxAnnotateLocal.storageRelief requires expectedDeviceId or expectedFsUuid when requireExternalMount = true.";
      }
      {
        assertion =
          !cfg.storageRelief.enable
          || cfg.storageRelief.archiveDir == cfg.storageRelief.externalMountPoint
          || lib.hasPrefix "${cfg.storageRelief.externalMountPoint}/" cfg.storageRelief.archiveDir;
        message = "services.luxnix.lxAnnotateLocal.storageRelief.archiveDir must stay inside storageRelief.externalMountPoint.";
      }
      {
        assertion =
          !cfg.storageRelief.enable
          || cfg.storageRelief.manifestDir == cfg.storageRelief.archiveDir
          || lib.hasPrefix "${cfg.storageRelief.archiveDir}/" cfg.storageRelief.manifestDir;
        message = "services.luxnix.lxAnnotateLocal.storageRelief.manifestDir must stay inside storageRelief.archiveDir.";
      }
      {
        assertion =
          !cfg.storageRelief.enable
          || cfg.storageRelief.stagingDir == cfg.storageRelief.archiveDir
          || lib.hasPrefix "${cfg.storageRelief.archiveDir}/" cfg.storageRelief.stagingDir;
        message = "services.luxnix.lxAnnotateLocal.storageRelief.stagingDir must stay inside storageRelief.archiveDir.";
      }
    ];
    services.luxnix.lxAnnotateLocal.django.extraSettings.IS_CENTRAL_NODE = mkIf cfg.hub.enable (
      mkDefault true
    );
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.enable =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable (mkDefault true);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.keyFile =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable (
        mkDefault cfg.runtime.vaultManagedEncryptedData.keyFilePath
      );
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.luksUuidFile =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable (
        mkDefault cfg.runtime.vaultManagedEncryptedData.luksUuidFilePath
      );
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.after =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        (mkBefore [ cfg.runtime.vaultManagedEncryptedData.setupService ]);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.requires =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        (mkBefore [ cfg.runtime.vaultManagedEncryptedData.setupService ]);
    services.luxnix.lxAnnotateLocal.runtime.masterKeyFile = mkDefault (
      if cfg.runtime.clustered.enable && cfg.runtime.clustered.sharedMasterKeyFile != null then
        cfg.runtime.clustered.sharedMasterKeyFile
      else if
        cfg.runtime.vaultManagedEncryptedData.enable
        && cfg.runtime.vaultManagedEncryptedData.manageMasterKey
      then
        cfg.runtime.vaultManagedEncryptedData.masterKeyFilePath
      else if cfg.runtime.autoGenerateMasterKey then
        cfg.runtime.autoGeneratedMasterKeyFilePath
      else
        null
    );
    services.luxnix.lxAnnotateLocal.database.host = mkIf (
      cfg.runtime.externalServices.postgresHost != null
    ) (mkForce cfg.runtime.externalServices.postgresHost);
    services.luxnix.lxAnnotateLocal.database.port = mkIf (
      cfg.runtime.externalServices.postgresPort != null
    ) (mkForce cfg.runtime.externalServices.postgresPort);

    roles.managed-secrets.customSecrets.lx_annotate_master_key_local =
      mkIf
        (
          cfg.runtime.autoGenerateMasterKey
          && !cfg.runtime.vaultManagedEncryptedData.enable
          && (
            cfg.runtime.masterKeyFile == null
            || cfg.runtime.masterKeyFile == cfg.runtime.autoGeneratedMasterKeyFilePath
          )
        )
        {
          path = toString cfg.runtime.autoGeneratedMasterKeyFilePath;
          owner = "root";
          group = config.luxnix.generic-settings.sensitiveServiceGroupName;
          permissions = "640";
          description = "Per-machine application master key for lx-annotate encrypted storage";
          generator = "${pkgs.openssl}/bin/openssl rand -base64 32 | tr -d '\n'";
        };

    roles.managed-secrets.customSecrets.lx_annotate_luks_key =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        {
          path = toString cfg.runtime.vaultManagedEncryptedData.keyFilePath;
          owner = "root";
          group = "root";
          permissions = "400";
          description = "Vault-backed LUKS key for lx-annotate encrypted data";
          customScript = true;
          refreshOnBoot = true;
          generator = ''
            HOSTNAME=${lib.escapeShellArg config.networking.hostName}
            VAULT_PATH=${
              lib.escapeShellArg (
                lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ]
                  cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate
              )
            }
            ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
              | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultKeyField}' \
              > "$TARGET_FILE"
          '';
        };

    roles.managed-secrets.customSecrets.lx_annotate_luks_uuid =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        {
          path = toString cfg.runtime.vaultManagedEncryptedData.luksUuidFilePath;
          owner = "root";
          group = "root";
          permissions = "400";
          description = "Vault-backed LUKS UUID for lx-annotate encrypted data";
          customScript = true;
          refreshOnBoot = true;
          generator = ''
            HOSTNAME=${lib.escapeShellArg config.networking.hostName}
            VAULT_PATH=${
              lib.escapeShellArg (
                lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ]
                  cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate
              )
            }
            ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
              | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultUuidField}' \
              | tr -d '\n' > "$TARGET_FILE"
          '';
        };

    roles.managed-secrets.customSecrets.lx_annotate_master_key =
      mkIf
        (
          cfg.runtime.vaultManagedEncryptedData.enable
          && cfg.runtime.vaultManagedEncryptedData.manageMasterKey
        )
        {
          path = toString cfg.runtime.vaultManagedEncryptedData.masterKeyFilePath;
          owner = "root";
          group = config.luxnix.generic-settings.sensitiveServiceGroupName;
          permissions = "640";
          description = "Vault-backed application master key for lx-annotate encrypted storage";
          customScript = true;
          refreshOnBoot = true;
          generator = ''
            HOSTNAME=${lib.escapeShellArg config.networking.hostName}
            VAULT_PATH=${
              lib.escapeShellArg (
                lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ]
                  cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate
              )
            }
            ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
              | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultMasterKeyField}' \
              | tr -d '\n' > "$TARGET_FILE"
            if [ ! -s "$TARGET_FILE" ]; then
              echo "ERROR: Vault returned an empty lx-annotate application master key from $VAULT_PATH."
              exit 1
            fi
            if [ -f "$SECRET_FILE" ] && ! ${pkgs.diffutils}/bin/cmp -s "$SECRET_FILE" "$TARGET_FILE"; then
              echo "ERROR: Vault lx-annotate application master key differs from the existing local key at $SECRET_FILE."
              echo "Refusing to replace it during managed-secrets refresh because that would break decryption of existing app-layer encrypted data."
              exit 1
            fi
          '';
        };

    services.luxnix.lxAnnotateLocal.django.djangoAllowedHosts = mkAfter [
      cfg.django.hostname
    ];
    services.luxnix.lxAnnotateLocal.django.sslCertificatePath = mkDefault defaultSslCertificatePath;
    services.luxnix.lxAnnotateLocal.django.sslKeyPath = mkDefault defaultSslKeyPath;
    services.luxnix.lxSsl.enable = mkDefault true;
    services.nginx = {
      enable = true;

      recommendedProxySettings = true;
      recommendedTlsSettings = true;

      virtualHosts."${cfg.django.hostname}" = {

        forceSSL = true;
        sslCertificate = sslCertPath;
        sslCertificateKey = sslKeyPath;
        # 1. Allow massive uploads for AI Models
        extraConfig = ''
          client_max_body_size 50G;
          proxy_request_buffering off;
        ''
        + optionalString sslCfg.enable ''
          ssl_stapling off;
          ssl_stapling_verify off;
          ${optionalString cfg.hub.transferApi.enable ''
            ssl_verify_client optional;
            ssl_client_certificate ${toString cfg.hub.transferApi.clientCaFile};
          ''}
        '';
        locations."/static/" = {
          # Must match STATIC_ROOT from Step 1
          alias = "${djangoStaticRootPath}/";
          extraConfig = "expires 30d; add_header Cache-Control 'public';";
        };

        locations."/media/" = {
          # Must match MEDIA_URL env var
          alias = "${envDataDir}/";
          extraConfig = "sendfile on; tcp_nopush on;";
        };

        locations."/protected_media/" = {
          alias = "${runtimeStorageRootPath}/";
          extraConfig = "internal; sendfile on; tcp_nopush on;";
        };

        locations."/api/media/videos/" = {
          proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
          proxyWebsockets = true;
          extraConfig = ''
            proxy_set_header Range $http_range;
            proxy_set_header If-Range $http_if_range;
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
          '';
        };

        locations."/" = {
          proxyPass = "http://127.0.0.1:${toString cfg.django.port}";

          # 2. Critical for Streaming/WebSockets
          proxyWebsockets = true;

          # 3. Timeout tuning for long AI Inference
          extraConfig = ''
            proxy_set_header X-Client-Cert-Verified $ssl_client_verify;
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;
            proxy_buffering off;
          '';
        };
      };
    };

    luxnix.generic-settings.postgres = {
      enable = mkDefault (!externalPostgresConfigured);
    };
    services.redis.servers."lx-annotate" = mkIf (!externalRedisConfigured) {
      enable = true;
      port = 6379;
      bind = "127.0.0.1";
      openFirewall = false;
      appendOnly = true;
      appendFsync = "everysec";
    };

    # Ensure directory structure exists with correct permissions
    users.users.nginx.extraGroups = [ "${endoreg-service-group-name}" ];

    systemd.tmpfiles.rules = [
      "d ${endoreg-service-user-home} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      # Important for make-based bootstrap:
      # do not pre-create ${repoDir} or repo-internal paths here. The seed clone
      # expects the checkout target to be absent (or at least empty), and creating
      # ${envDataDir}/${staticRootPath} makes it non-empty before git runs.

      # 1. The Parent Directory: systemd owns creation via StateDirectory, but
      # tmpfiles keeps permissions stable across rebuilds and restarts.
      "d /var/lib/lx-annotate 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z /var/lib/lx-annotate 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

      # 2. The SSL Directory: keep the directory permissions stable. Do not
      # mutate TLS material from nginx preStart because that path inherits the
      # nginx service sandbox and may trip seccomp or read-only mounts.
      "d ${sslCfg.sslDir} 0750 root nginx - -"
      "z ${sslCfg.sslDir} 0750 root nginx - -"

      # Frontend/static output lives outside the git checkout so it stays writable
      # even with systemd filesystem protections enabled.
      "d ${runtimeWheelRootPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeWheelRootPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeWheelVenvPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeWheelVenvPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeDataRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeDataRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.runtime.modelTrainingStagingRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} 7d -"
      "z ${cfg.runtime.modelTrainingStagingRoot} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStreamableVideoRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStreamableVideoRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStreamableVideoRawRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStreamableVideoRawRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStreamableVideoProcessedRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStreamableVideoProcessedRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStorageRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStorageRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeIoImportRootPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeIoImportRootPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeWatcherVideoDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeWatcherReportDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeWatcherPreanonymizedDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeSapImportDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeMoverStagingDirPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      # Desktop and service-user workflows should use this symlink as a
      # convenience access path only. It points back into the canonical
      # protected runtime import tree and is not a second IO root.
      "L ${serviceUserIoAccessLinkPath} - - - - ${runtimeIoImportRootPath}"
      "d ${runtimeStaticRootPath} 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStaticRootPath}/.vite 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStaticRootPath} 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStaticRootPath}/.vite 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.dataCleanup.archiveDir} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.dataCleanup.archiveDir} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${hubRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${hubRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${hubRootPath}/backup 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${hubRootPath}/backup 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.hub.backup.incomingDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.hub.backup.incomingDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.hub.backup.snapshotDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.hub.backup.snapshotDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.hub.backup.manifestDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.hub.backup.manifestDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

      # TLS material normalization is handled by dedicated pre-nginx services
      # such as generate-lx-ssl, not by nginx preStart.
    ]
    ++ lib.optionals (!config.roles.endoreg-client.enable) [
      # Create the config subdirectory (handled by endoreg-client role when enabled)
      "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
    ];

    system.activationScripts.lxAnnotateRuntimePathMigration = ''
      hub_backup_dir="${hubRootPath}/backup"
      old_ssl_dir="/var/lib/lx-annotate/ssl"
      new_ssl_dir="${toString sslCfg.sslDir}"

      if [ -d "${hubRootPath}" ]; then
        ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} "$hub_backup_dir"
      fi

      if [ "$old_ssl_dir" != "$new_ssl_dir" ] && [ -d "$old_ssl_dir" ]; then
        ${pkgs.coreutils}/bin/install -d -m 0750 -o root -g nginx "$new_ssl_dir"
        ${pkgs.findutils}/bin/find "$old_ssl_dir" -maxdepth 1 -type f -exec ${pkgs.coreutils}/bin/cp -n -- {} "$new_ssl_dir"/ \;
        ${pkgs.coreutils}/bin/chown -R root:nginx "$new_ssl_dir"
        [ -f "${toString sslCfg.keyPath}" ] && ${pkgs.coreutils}/bin/chmod 0640 "${toString sslCfg.keyPath}"
        [ -f "${toString sslCfg.certPath}" ] && ${pkgs.coreutils}/bin/chmod 0644 "${toString sslCfg.certPath}"
      fi
    '';

    systemd.services.lx-annotate-encrypted-data = mkIf cfg.runtime.managedEncryptedData.enable {
      description = "Unlock and mount encrypted data volume for lx-annotate";
      wantedBy = [ "multi-user.target" ];
      before = [ "lx-annotate-boot.service" ];
      after = [ "systemd-tmpfiles-setup.service" ] ++ cfg.runtime.managedEncryptedData.after;
      requires = cfg.runtime.managedEncryptedData.requires;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        Group = "root";
        ExecStart = "${lxAnnotateEncryptedDataMountScript}/bin/lx-annotate-encrypted-data-mount";
        ExecStop = "${lxAnnotateEncryptedDataUmountScript}/bin/lx-annotate-encrypted-data-umount";
        TimeoutStartSec = "2min";
        TimeoutStopSec = "2min";
      };
      path = [
        pkgs.coreutils
        pkgs.cryptsetup
        pkgs.util-linux
      ];
    };

    systemd.services.lx-annotate-migrate = mkIf useWheelRuntime {
      description = "Apply lx-annotate database migrations for wheel runtime";
      before = [ "lx-annotate-boot.service" ];
      wants = localPostgresServiceUnits ++ encryptionServiceUnits;
      after = [
        "systemd-tmpfiles-setup.service"
      ]
      ++ localPostgresServiceUnits
      ++ localPostgresSetupUnits
      ++ lib.optionals cfg.dataRecovery.enable [
        "lx-annotate-data-recovery.service"
      ]
      ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStartPre = [
          stopWheelCeleryWorkersPreStart
          wheelRuntimePreStart
        ];
        ExecStart = "${runLocalMigrateWheelScript}/bin/${migrateWheelScriptName}";
        Environment = appServiceEnvironment;
        TimeoutStartSec = "10min";
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = appReadWritePaths;
      };
    };

    systemd.services.lx-annotate-load-base-data = mkIf useWheelRuntime {
      description = "Load lx-annotate base data for wheel runtime";
      before = [ "lx-annotate-boot.service" ];
      after = [ "lx-annotate-migrate.service" ] ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = [ "lx-annotate-migrate.service" ] ++ encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStartPre = [
          stopWheelCeleryWorkersPreStart
          wheelRuntimePreStart
        ];
        ExecStart = "${runLocalLoadBaseDataWheelScript}/bin/${loadBaseDataWheelScriptName}";
        Environment = appServiceEnvironment;
        TimeoutStartSec = "10min";
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = appReadWritePaths;
      };
    };

    systemd.services."lx-annotate-boot" = {
      description =
        if useWheelRuntime then
          "Install lx-annotate wheel and run ASGI service"
        else
          "Clone or pull lx-annotate and run prod-server";
      wantedBy = [ "multi-user.target" ];
      wants = [
        "nginx.service"
      ]
      ++ localRedisServiceUnits
      ++ localPostgresSetupUnits
      ++ wheelBootstrapUnits
      ++ masterKeyCheckUnits
      ++ encryptionServiceUnits;
      requires =
        lib.optionals cfg.dataRecovery.enable [ "lx-annotate-data-recovery.service" ]
        ++ wheelBootstrapUnits
        ++ masterKeyCheckUnits
        ++ encryptionServiceUnits;
      after = [
        "endoreg-django-setup.service"
        "systemd-tmpfiles-setup.service"
      ]
      ++ localRedisServiceUnits
      ++ localPostgresSetupUnits
      ++ lib.optionals cfg.dataRecovery.enable [
        "lx-annotate-data-recovery.service"
      ]
      ++ wheelBootstrapUnits
      ++ masterKeyCheckUnits
      ++ encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        WorkingDirectory = if useWheelRuntime then runtimeWorkingDir else endoreg-service-user-home;
        StateDirectory = "lx-annotate";
        StateDirectoryMode = "0750";
        Environment = appServiceEnvironment;

        TimeoutStartSec = "5min";
        ExecStartPre = [
          "+${pkgs.writeShellScript "lx-annotate-pre-start" ''
            set -euo pipefail

            # Prefer frontend/streaming availability over intake processing if
            # the app is being started or restarted during a maintenance drain.
            ${pkgs.systemd}/bin/systemctl stop lx-annotate-filewatcher.service >/dev/null 2>&1 || true

            # 0. Ensure key writable directories exist with the expected owner.
            ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${endoreg-service-user-home}
            ${optionalString (!useWheelRuntime)
              "${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${repoDir}"
            }
            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
            ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envDataDir}
            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeWheelRootPath}
            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeWheelVenvPath}

            # 1b. Keep runtime static output outside the checkout and expose it at
            # ${repoStaticRootPath} is handled after checkout in the main service
            # script to avoid interfering with first-time clones.
            ${pkgs.coreutils}/bin/install -d -m 0775 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeStaticRootPath}
            ${pkgs.coreutils}/bin/install -d -m 0775 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeStaticRootPath}/.vite

            # 2. Handle the Password File securely
            SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
            TARGET_PWD="${envConfDir}/db_pwd"

            if [ -f "$SOURCE_PWD" ]; then
               echo "Copying database password..."
               cp "$SOURCE_PWD" "$TARGET_PWD"
               
               # Give ownership to the service user
               chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
               
               # Secure it
               chmod 600 "$TARGET_PWD"
            else
               echo "WARNING: Password file $SOURCE_PWD not found!"
            fi

            [ -f "${cfg.django.keycloakSecretFile}" ] && chown root:${endoreg-service-group-name} "${cfg.django.keycloakSecretFile}"
            [ -f "${cfg.django.keycloakSecretFile}" ] && chmod 640 "${cfg.django.keycloakSecretFile}"
          ''}"
        ]
        ++ lib.optionals (!useWheelRuntime) [
          "${lxAnnotateBootstrapScript}/bin/lx-annotate-bootstrap"
        ];
        ExecStart =
          if useWheelRuntime then
            "${runLocalLxAnnotateWheelScript}/bin/${scriptName}"
          else
            "${runLocalLxAnnotateStartScript}/bin/lx-annotate-start";
        Restart = "on-failure";
        RestartSec = "5s";
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
        ];
        # Resource limits
        MemoryHigh = cfg.runtime.limits.memoryHigh;
        MemoryMax = cfg.runtime.limits.memoryMax;
        CPUQuota = cfg.runtime.limits.cpuQuota;
        Nice = 10;

        # 2. Disk I/O: leave headroom for the rest of the system during startup
        IOSchedulingClass = "best-effort";
        IOSchedulingPriority = 6;

        # 3. Memory Protection
        # Prefer killing/restarting this service over killing core host processes.
        OOMScoreAdjust = 250;
      };
    };
    systemd.services.lx-annotate-data-recovery = mkIf cfg.dataRecovery.enable {
      description = "Recover legacy lx-annotate data into runtime storage";
      wantedBy = [ "multi-user.target" ];
      before = [ "lx-annotate-boot.service" ];
      wants = localPostgresServiceUnits ++ encryptionServiceUnits;
      after = [ "systemd-tmpfiles-setup.service" ] ++ localPostgresServiceUnits ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = endoreg-service-user-home;
        ExecStartPre = [
          "+${pkgs.writeShellScript "lx-annotate-data-recovery-pre-start" ''
            set -euo pipefail
            SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
            TARGET_PWD="${envConfDir}/db_pwd"

            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
            if [ -f "$SOURCE_PWD" ]; then
              cp "$SOURCE_PWD" "$TARGET_PWD"
              chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
              chmod 600 "$TARGET_PWD"
            else
              echo "WARNING: data-recovery password file $SOURCE_PWD not found"
            fi
          ''}"
        ];
        ExecStart = "${runLocalDataRecoveryScript}/bin/runLxAnnotateDataRecovery";
        Environment = [ runtimeLdLibraryPathEnv ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          "/var/lib/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-master-key-check = mkIf useWheelRuntime {
      description = "Validate lx-annotate application master key against encrypted storage";
      wantedBy = [ "multi-user.target" ];
      before = [ "lx-annotate-boot.service" ];
      after = [
        "systemd-tmpfiles-setup.service"
      ]
      ++ localPostgresServiceUnits
      ++ localPostgresSetupUnits
      ++ wheelBootstrapUnits
      ++ encryptionServiceUnits;
      wants = localPostgresServiceUnits ++ encryptionServiceUnits;
      requires = wheelBootstrapUnits ++ encryptionServiceUnits;
      restartTriggers = [ runLocalMasterKeyCheckWheelScript ];
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStartPre = [ wheelRuntimePreStart ];
        ExecStart = "${runLocalMasterKeyCheckWheelScript}/bin/${masterKeyCheckScriptName}";
        Environment = appServiceEnvironment;
        TimeoutStartSec = "10min";
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = appReadWritePaths;
      };
    };
    systemd.services.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
      description = "Move duplicate anonymized lx-annotate payload into external archive storage";
      after = [
        "systemd-tmpfiles-setup.service"
        "endoreg-mount-persisting-storage.service"
      ]
      ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = endoreg-service-user-home;
        ExecStart = "${runLocalDataCleanupScript}/bin/runLxAnnotateDataCleanup";
        Environment = [ runtimeLdLibraryPathEnv ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          cfg.dataCleanup.archiveDir
          "/var/lib/lx-annotate"
          "/var/endoreg-service-user/lx-annotate"
          config.roles.endoreg-client.paths.storagePersistingMountPoint
        ];
      };
    };
    systemd.timers.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
      description = "Periodic duplicate cleanup for anonymized lx-annotate legacy storage";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "15m";
        OnCalendar = cfg.dataCleanup.onCalendar;
        Unit = "lx-annotate-data-cleanup.service";
      };
    };
    systemd.services.lx-annotate-emergency-storage-relief = mkIf cfg.storageRelief.enable {
      description = "Emergency lx-annotate storage relief to verified external archive";
      after = [
        "systemd-tmpfiles-setup.service"
      ]
      ++ localPostgresServiceUnits
      ++ localPostgresSetupUnits
      ++ lib.optionals cfg.storageRelief.requireExternalMount [
        "endoreg-mount-persisting-storage.service"
      ]
      ++ encryptionServiceUnits;
      wants =
        lib.optionals cfg.storageRelief.requireExternalMount [
          "endoreg-mount-persisting-storage.service"
        ]
        ++ encryptionServiceUnits;
      requires =
        lib.optionals cfg.storageRelief.requireExternalMount [
          "endoreg-mount-persisting-storage.service"
        ]
        ++ encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [
          envDataDir
        ]
        ++ lib.optionals cfg.storageRelief.requireExternalMount [
          cfg.storageRelief.externalMountPoint
        ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStartPre = [
          "+${pkgs.writeShellScript "lx-annotate-emergency-storage-relief-pre-start" ''
            set -euo pipefail
            SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
            TARGET_PWD="${envConfDir}/db_pwd"

            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
            if [ -f "$SOURCE_PWD" ]; then
              cp "$SOURCE_PWD" "$TARGET_PWD"
              chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
              chmod 600 "$TARGET_PWD"
            else
              echo "WARNING: emergency-storage-relief password file $SOURCE_PWD not found"
            fi
          ''}"
        ];
        ExecStart = "${runLocalEmergencyStorageReliefScript}/bin/${emergencyStorageReliefScriptName}";
        Environment = appServiceEnvironment;
        TimeoutStartSec = "infinity";
        Nice = 19;
        IOSchedulingClass = "idle";
        OOMScoreAdjust = 900;
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          cfg.storageRelief.externalMountPoint
        ];
      };
      path = [
        pkgs.coreutils
        pkgs.findutils
        pkgs.util-linux
      ];
    };
    systemd.timers.lx-annotate-emergency-storage-relief =
      mkIf (cfg.storageRelief.enable && cfg.storageRelief.timer.enable)
        {
          description = "Periodic emergency lx-annotate storage relief";
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnBootSec = "20m";
            OnCalendar = cfg.storageRelief.timer.onCalendar;
            Unit = "lx-annotate-emergency-storage-relief.service";
          };
        };
    systemd.services.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
      description = "Create protected lx-annotate hub runtime snapshots";
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = "${runLocalHubBackupScript}/bin/runLxAnnotateHubBackup";
        Environment = [ runtimeLdLibraryPathEnv ];
        ReadWritePaths = [
          envDataDir
          cfg.hub.backup.incomingDir
          cfg.hub.backup.snapshotDir
          cfg.hub.backup.manifestDir
          runtimeRootPath
        ];
      };
      path = [
        pkgs.coreutils
        pkgs.findutils
        pkgs.jq
        pkgs.rsync
      ];
    };
    systemd.timers.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
      description = "Periodic protected snapshots for the lx-annotate hub node";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "10m";
        OnCalendar = cfg.hub.backup.onCalendar;
        Unit = "lx-annotate-hub-backup.service";
      };
    };
    systemd.services.lx-annotate-filewatcher =
      mkIf (!useWheelRuntime || cfg.runtime.commands.fileWatcher != null)
        {
          description = "Drain lx-annotate watcher intake files";
          after = localRedisServiceUnits ++ localPostgresServiceUnits ++ encryptionServiceUnits;
          wants = localRedisServiceUnits ++ encryptionServiceUnits;
          requires = localRedisServiceUnits ++ encryptionServiceUnits;
          unitConfig = encryptedDataMountUnitConfig;

          serviceConfig = {
            Type = "oneshot";
            User = endoreg-service-user-name; # Or whatever user runs the app
            Group = endoreg-service-group-name;
            WorkingDirectory = runtimeWorkingDir;
            ExecStart =
              if useWheelRuntime then
                "${runLocalFileWatcherWheelScript}/bin/${watcherScriptName}"
              else
                "${runLocalFileWatcherScript}/bin/${watcherScriptName}";
            Environment = [
              servicePathEnv
              "LX_ANNOTATE_ENCRYPTED_DATA_DIR=${runtimeDataRootPath}"
              "WATCHER_VIDEO_DIR=${runtimeWatcherVideoDirPath}"
              "WATCHER_REPORT_DIR=${runtimeWatcherReportDirPath}"
              "WATCHER_PREANONYMIZED_DIR=${runtimeWatcherPreanonymizedDirPath}"
              nixPathEnv
              runtimeFfmpegLdLibraryPathEnv
              "DJANGO_DATA_DIR=${runtimeDataRootPath}/storage" # Fixes the storage check
              deploymentRoleEnv
              hubModeEnv
              enableHubTransfersEnv
              hubTransferRequireSecureTransportEnv
              hubTransferRequireMtlsEnv
              hubTransferMtlsMetaKeyEnv
              hubTransferMtlsMetaValueEnv
              defaultCenterEnv
            ];
            MemoryHigh = "1G";
            MemoryMax = "2G";
            CPUQuota = "35%";
            KillSignal = "SIGINT";
            TimeoutStopSec = "30min";

            # 1. CPU Priority: Lower priority (Higher "Nice" value = nicer to others)
            Nice = 19;

            # 2. Disk I/O Class: "idle"
            # This process will only get disk time when no other process needs it.
            # This solves the streaming stutter immediately.
            IOSchedulingClass = "idle";

            # 3. OOM Score: If RAM runs out, kill this service first, never the web server.
            OOMScoreAdjust = 1000;
            ReadWritePaths = appReadWritePaths;
          };
        };
    systemd.paths.lx-annotate-filewatcher =
      mkIf (!useWheelRuntime || cfg.runtime.commands.fileWatcher != null)
        {
          description = "Trigger lx-annotate watcher when intake files are dropped";
          wantedBy = [ "multi-user.target" ];
          pathConfig = {
            # These paths are also the publish destinations for move-my-files.
            # Keep both sides derived from runtime.intakeDirs.
            PathChanged = [
              runtimeWatcherVideoDirPath
              runtimeWatcherReportDirPath
              runtimeWatcherPreanonymizedDirPath
            ];
            Unit = "lx-annotate-filewatcher.service";
            MakeDirectory = true;
          };
        };
    systemd.timers.lx-annotate-filewatcher =
      mkIf (!useWheelRuntime || cfg.runtime.commands.fileWatcher != null)
        {
          description = "Manual lx-annotate watcher intake drain timer";
          # Intentionally not enabled by default: intake processing is heavy I/O and
          # should be started from an explicit maintenance/app-control path.
          timerConfig = {
            OnBootSec = "20m";
            OnUnitInactiveSec = "30m";
            Persistent = true;
            Unit = "lx-annotate-filewatcher.service";
          };
        };
    systemd.services.lx-annotate-celery-worker = mkIf celeryWorkerEnabled (mkCeleryWorkerService {
      description = "Celery worker for lx-annotate default and maintenance jobs";
      execStart =
        if useWheelRuntime then
          "${runLocalCeleryWorkerWheelScript}/bin/${celeryWorkerScriptName}"
        else
          "${runLocalCeleryWorkerScript}/bin/${celeryWorkerScriptName}";
      memoryHigh = cfg.runtime.workerLimits.memoryHigh;
      memoryMax = cfg.runtime.workerLimits.memoryMax;
      cpuQuota = cfg.runtime.workerLimits.cpuQuota;
      nice = cfg.runtime.workerPools.maintenance.nice;
      oomScoreAdjust = cfg.runtime.workerPools.maintenance.oomScoreAdjust;
    });
    systemd.services.lx-annotate-celery-pipeline-worker =
      mkIf celeryWorkerEnabled
        (mkCeleryWorkerService {
          description = "Celery worker for lx-annotate upload and anonymization pipeline jobs";
          execStart =
            if useWheelRuntime then
              "${runLocalCeleryPipelineWorkerWheelScript}/bin/${celeryPipelineWorkerScriptName}"
            else
              "${runLocalCeleryPipelineWorkerScript}/bin/${celeryPipelineWorkerScriptName}";
          memoryHigh = cfg.runtime.workerPools.pipeline.memoryHigh;
          memoryMax = cfg.runtime.workerPools.pipeline.memoryMax;
          cpuQuota = cfg.runtime.workerPools.pipeline.cpuQuota;
          nice = cfg.runtime.workerPools.pipeline.nice;
          oomScoreAdjust = cfg.runtime.workerPools.pipeline.oomScoreAdjust;
          startupDelaySec = cfg.runtime.workerStartupDelaySec;
        });
    systemd.services.lx-annotate-celery-ffmpeg-worker =
      mkIf celeryWorkerEnabled
        (mkCeleryWorkerService {
          description = "Celery worker for lx-annotate low-priority FFmpeg media jobs";
          execStart =
            if useWheelRuntime then
              "${runLocalCeleryFfmpegWorkerWheelScript}/bin/${celeryFfmpegWorkerScriptName}"
            else
              "${runLocalCeleryFfmpegWorkerScript}/bin/${celeryFfmpegWorkerScriptName}";
          memoryHigh = cfg.runtime.workerPools.ffmpeg.memoryHigh;
          memoryMax = cfg.runtime.workerPools.ffmpeg.memoryMax;
          cpuQuota = cfg.runtime.workerPools.ffmpeg.cpuQuota;
          nice = cfg.runtime.workerPools.ffmpeg.nice;
          oomScoreAdjust = cfg.runtime.workerPools.ffmpeg.oomScoreAdjust;
          wantedBy = ffmpegWorkerBootWantedBy;
          partOf = [ "lx-annotate-boot.service" ];
          wants = ffmpegWorkerBootRequires;
          requires = ffmpegWorkerBootRequires;
          restart = if ffmpegWorkerMode == "always" then "always" else "no";
          startupDelaySec = if ffmpegWorkerMode == "always" then cfg.runtime.workerStartupDelaySec else null;
        });
    systemd.services.lx-annotate-celery-frame-extraction-worker =
      mkIf celeryWorkerEnabled
        (mkCeleryWorkerService {
          description = "Celery worker for lx-annotate FFmpeg frame extraction jobs";
          execStart =
            if useWheelRuntime then
              "${runLocalCeleryFrameExtractionWorkerWheelScript}/bin/${celeryFrameExtractionWorkerScriptName}"
            else
              "${runLocalCeleryFrameExtractionWorkerScript}/bin/${celeryFrameExtractionWorkerScriptName}";
          memoryHigh = cfg.runtime.workerPools.frameExtraction.memoryHigh;
          memoryMax = cfg.runtime.workerPools.frameExtraction.memoryMax;
          cpuQuota = cfg.runtime.workerPools.frameExtraction.cpuQuota;
          nice = cfg.runtime.workerPools.frameExtraction.nice;
          oomScoreAdjust = cfg.runtime.workerPools.frameExtraction.oomScoreAdjust;
          wantedBy = frameExtractionWorkerBootWantedBy;
          partOf = [ "lx-annotate-boot.service" ];
          wants = frameExtractionWorkerBootRequires;
          requires = frameExtractionWorkerBootRequires;
          restart = if frameExtractionWorkerMode == "always" then "always" else "no";
          runtimeMaxSec =
            if frameExtractionWorkerMode == "maintenance-window" then
              cfg.runtime.frameExtractionWorker.runtimeMaxSec
            else
              null;
          timeoutStopSec =
            if frameExtractionWorkerMode == "maintenance-window" then
              cfg.runtime.frameExtractionWorker.timeoutStopSec
            else
              null;
          extraServiceConfig = optionalAttrs (frameExtractionWorkerMode == "maintenance-window") {
            KillSignal = "SIGTERM";
          };
        });
    systemd.services.lx-annotate-celery-inference-worker =
      mkIf celeryWorkerEnabled
        (mkCeleryWorkerService {
          description = "Celery worker for lx-annotate AI temporal inference jobs";
          execStart =
            if useWheelRuntime then
              "${runLocalCeleryInferenceWorkerWheelScript}/bin/${celeryInferenceWorkerScriptName}"
            else
              "${runLocalCeleryInferenceWorkerScript}/bin/${celeryInferenceWorkerScriptName}";
          memoryHigh = cfg.runtime.workerPools.inference.memoryHigh;
          memoryMax = cfg.runtime.workerPools.inference.memoryMax;
          cpuQuota = cfg.runtime.workerPools.inference.cpuQuota;
          nice = cfg.runtime.workerPools.inference.nice;
          oomScoreAdjust = cfg.runtime.workerPools.inference.oomScoreAdjust;
          wantedBy = inferenceWorkerBootWantedBy;
          partOf = [ "lx-annotate-boot.service" ];
          wants = inferenceWorkerBootRequires;
          requires = inferenceWorkerBootRequires;
          restart = if inferenceWorkerMode == "always" then "always" else "no";
          timeoutStopSec = "45min";
          extraServiceConfig = {
            KillSignal = "SIGTERM";
          };
        });
    systemd.services.lx-annotate-celery-training-worker =
      mkIf celeryWorkerEnabled
        (mkCeleryWorkerService {
          description = "Celery worker for lx-annotate GPU model training jobs";
          execStart =
            if useWheelRuntime then
              "${runLocalCeleryTrainingWorkerWheelScript}/bin/${celeryTrainingWorkerScriptName}"
            else
              "${runLocalCeleryTrainingWorkerScript}/bin/${celeryTrainingWorkerScriptName}";
          memoryHigh = cfg.runtime.workerPools.training.memoryHigh;
          memoryMax = cfg.runtime.workerPools.training.memoryMax;
          cpuQuota = cfg.runtime.workerPools.training.cpuQuota;
          nice = cfg.runtime.workerPools.training.nice;
          oomScoreAdjust = cfg.runtime.workerPools.training.oomScoreAdjust;
          wantedBy = trainingWorkerBootWantedBy;
          partOf = [ "lx-annotate-boot.service" ];
          wants = trainingWorkerBootRequires;
          requires = trainingWorkerBootRequires;
          restart = if trainingWorkerMode == "always" then "always" else "no";
          timeoutStopSec = "45min";
          extraServiceConfig = {
            KillSignal = "SIGTERM";
          };
        });
    systemd.timers.lx-annotate-celery-frame-extraction-worker =
      mkIf (celeryWorkerEnabled && frameExtractionWorkerMode == "maintenance-window")
        {
          description = "Maintenance window for lx-annotate FFmpeg frame extraction jobs";
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnCalendar = cfg.runtime.frameExtractionWorker.onCalendar;
            Persistent = cfg.runtime.frameExtractionWorker.persistentTimer;
            RandomizedDelaySec = cfg.runtime.frameExtractionWorker.randomizedDelaySec;
            Unit = "lx-annotate-celery-frame-extraction-worker.service";
          };
        };
    systemd.services.lx-annotate-acceptance = {
      description = "Run lx-annotate encrypted-storage and nginx acceptance checks";
      after = [
        "lx-annotate-boot.service"
        "nginx.service"
      ]
      ++ encryptionServiceUnits;
      wants = [
        "lx-annotate-boot.service"
        "nginx.service"
      ]
      ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart =
          if useWheelRuntime then
            "${runLocalAcceptanceWheelScript}/bin/${acceptanceScriptName}"
          else
            "${runLocalAcceptanceScript}/bin/${acceptanceScriptName}";
        Environment = appServiceEnvironment;
        ReadWritePaths = appReadWritePaths;
      };
    };
    systemd.services.lx-annotate-video-streamable-migration = mkIf cfg.streamableMigration.enable {
      description = "Migrate lx-annotate videos into streamable protected storage";
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      requires = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = "${lxAnnotateMigrateVideoStreamableStorageScript}/bin/${migrateVideoStreamableStorageScriptName}";
        Environment = appServiceEnvironment;
        TimeoutStartSec = "infinity";
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-sap-import = {
      description = "Convert SAP IS-H zip drops into preanonymized watcher payload";
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart =
          if useWheelRuntime then
            "${runLocalSapImportWheelScript}/bin/${sapImportScriptName}"
          else
            "${runLocalSapImportScript}/bin/${sapImportScriptName}";
        Environment = appServiceEnvironment;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.paths.lx-annotate-sap-import = {
      description = "Trigger SAP IS-H zip conversion when SAP drops exist";
      wantedBy = [ "multi-user.target" ];
      pathConfig = {
        PathExistsGlob = [ "${runtimeSapImportDirPath}/*.zip" ];
        Unit = "lx-annotate-sap-import.service";
        MakeDirectory = true;
      };
    };

    systemd.services.lx-annotate-export-frames =
      mkIf (!useWheelRuntime || cfg.runtime.commands.exportFrames != null)
        {
          description = "Export annotated frames for lx-annotate";
          after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
          wants = encryptionServiceUnits;
          requires = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
          unitConfig = encryptedDataMountUnitConfig;

          serviceConfig = {
            Type = "oneshot";
            User = endoreg-service-user-name;
            WorkingDirectory = runtimeWorkingDir;
            ExecStart =
              if useWheelRuntime then
                "${runLocalExportFramesWheelScript}/bin/${exportFramesScriptName}"
              else
                "${runLocalExportFramesScript}/bin/${exportFramesScriptName}";
            Environment = appServiceEnvironment;
            ReadWritePaths = appReadWritePaths;
          };
        };
    systemd.services.nginx.serviceConfig = {
      # -5 gives Nginx slightly higher priority than standard processes
      Nice = -5;

      # Give Nginx "Best Effort" disk access, with the highest priority (0)
      # This ensures video chunks are read from disk before anything else
      IOSchedulingClass = "best-effort";
      IOSchedulingPriority = 0;

      # Protect Nginx from being killed if RAM runs out
      OOMScoreAdjust = -500;
    };
  };
}
