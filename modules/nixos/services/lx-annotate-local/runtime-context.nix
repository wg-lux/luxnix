{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.lxAnnotateLocal;
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;
  sslCfg = lib.attrByPath [ "services" "luxnix" "lxSsl" ] {
    enable = false;
    sslDir = "/var/lib/lx-annotate-ssl";
    certPath = "/var/lib/lx-annotate-ssl/lx-annotate-selfsigned.crt";
    keyPath = "/var/lib/lx-annotate-ssl/lx-annotate-selfsigned.key";
  } config;

  defaultSslCertificatePath = sslCfg.certPath;
  defaultSslKeyPath = sslCfg.keyPath;

  adminName = config.user.admin.name;
  scriptName = "runLocalLxAnnotate";
  exportFramesScriptName = "runLocalExportFrames";

  gitURL = cfg.source.url;
  repoDirName = "lx-annotate";
  branchName = cfg.source.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home =
    config.user.endoreg-service-user.extraOptions.home or "/var/${endoreg-service-user-name}";
  endoreg-service-group-name = config.user.endoreg-service-user.group;
  runtimeRootPath = "/var/lib/lx-annotate";
  repoDir = "${endoreg-service-user-home}/${repoDirName}";
  repoStaticRootPath = "${repoDir}/staticfiles";
  runtimeDataRootPath = cfg.runtime.encryptedDataDir;
  resolveRuntimeDataPath = path:
    let
      pathString = toString path;
    in
    if lib.hasPrefix "/" pathString then
      pathString
    else if pathString == "data" then
      runtimeDataRootPath
    else if lib.hasPrefix "data/" pathString then
      "${runtimeDataRootPath}/${lib.removePrefix "data/" pathString}"
    else
      "${runtimeDataRootPath}/${pathString}";
  # Canonical protected runtime layout:
  # - runtimeDataRootPath is the single protected root
  # - runtimeStorageRootPath is the managed storage subtree under that root
  # - runtimeIoImportRootPath is the intake/workflow subtree under that root
  #
  # Anything under the service-user home is only an access path or symlink and
  # must not be treated as an independent runtime root.
  runtimeStorageRootPath = "${runtimeDataRootPath}/storage";
  runtimeIoImportRootPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.importRoot;
  runtimeWatcherVideoDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.video;
  runtimeWatcherReportDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.report;
  runtimeWatcherPreanonymizedDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.preanonymized;
  runtimeSapImportDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.sap;
  runtimeSapImportProcessedDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.sapProcessed;
  runtimeSapImportFailedDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.sapFailed;
  runtimeMoverStagingDirPath = resolveRuntimeDataPath cfg.runtime.intakeDirs.moverStaging;
  runtimeStreamableVideoRootPath = "${runtimeStorageRootPath}/streamable_videos";
  runtimeStreamableVideoRawRootPath = "${runtimeStreamableVideoRootPath}/raw";
  runtimeStreamableVideoProcessedRootPath = "${runtimeStreamableVideoRootPath}/processed";
  envNginxProtectedMediaUrl = "/protected_media/";
  runtimeStaticRootPath = "/var/lib/lx-annotate/staticfiles";
  runtimeWheelRootPath = "${endoreg-service-user-home}/lx-annotate-wheel";
  runtimeWheelVenvPath = "${runtimeWheelRootPath}/.venv";
  useWheelRuntime = cfg.runtime.mode == "wheel";
  runtimeWorkingDir = if useWheelRuntime then runtimeWheelRootPath else repoDir;
  staticRootPath = runtimeStaticRootPath;
  djangoStaticRootPath =
    if useWheelRuntime then
      "${runtimeWheelRootPath}/staticfiles"
    else
      repoStaticRootPath;
  viteSourcePath = "${repoDir}/static";

  envDataDir = runtimeDataRootPath;
  envConfDir =
    if useWheelRuntime then
      "${runtimeWheelRootPath}/${cfg.django.confDir}"
    else
      "${repoDir}/${cfg.django.confDir}";
  makeCacheDir = "${envConfDir}/make-cache";
  envConfTemplateDir =
    if useWheelRuntime then
      "${runtimeWheelRootPath}/${cfg.django.confTemplateDir}"
    else
      "${repoDir}/${cfg.django.confTemplateDir}";
  envDjangoModule = cfg.django.djangoModule;
  envHttpProtocol =
    if cfg.django.httpProtocol != "http" then
      cfg.django.httpProtocol
    else if cfg.django.useHttps then
      "https"
    else
      "http";
  envDjangoHost = cfg.django.hostname;
  envDjangoPort = toString cfg.django.port;
  envBaseUrl =
    if cfg.django.baseUrl != null then
      cfg.django.baseUrl
    else
      "${envHttpProtocol}://${envDjangoHost}:${envDjangoPort}";
  sslDir = sslCfg.sslDir;
  sslKeyPath = sslCfg.keyPath;
  sslCertPath = sslCfg.certPath;

  envSystemdFilePath = "${runtimeRootPath}/.env.systemd";
  pythonInterpreter = "${cfg.runtime.pythonPackage}/bin/python3";
  wheelFilePath = if cfg.runtime.wheelPath == null then "" else toString cfg.runtime.wheelPath;
  packageVersion = cfg.runtime.packageVersion;
  managedEncryptedDataServiceName = "lx-annotate-encrypted-data.service";
  encryptionServiceUnits =
    if cfg.runtime.managedEncryptedData.enable then
      [ managedEncryptedDataServiceName ]
    else
      lib.optionals (cfg.runtime.encryptionService != null) [ cfg.runtime.encryptionService ];
  encryptedDataMountOptions =
    lib.concatStringsSep "," cfg.runtime.managedEncryptedData.mountOptions;

  makeAbsolute = path:
    if lib.hasPrefix "/" path then path else "${runtimeWorkingDir}/${path}";

  envAssetDir = makeAbsolute cfg.django.assetDir;
  envStaticUrl = cfg.django.staticUrl;
  envMediaUrl = cfg.django.mediaUrl;
  envRunVideoTests = if cfg.django.runVideoTests then "true" else "false";
  envSkipExpensiveTests = if cfg.django.skipExpensiveTests then "true" else "false";
  envViteEnableDebug = if cfg.debug.enable then "true" else "false";
  envAllowedHosts = lib.concatStringsSep "," cfg.django.djangoAllowedHosts;
  envCorsAllowedOrigins = lib.concatStringsSep "," cfg.django.corsAllowedOrigins;

  settingsProfile = cfg.django.settingsProfile;
  envIsCentralNode = cfg.django.extraSettings.IS_CENTRAL_NODE or false;
  envAnnotateDjangoSettingsModule = "lx_annotate.settings.settings_prod";
  envDjangoEnv = "production";
  envCentralNodeFlag =
    if envIsCentralNode || settingsProfile == "central" then "true" else "false";
  envDeploymentRole = cfg.runtime.deploymentRole;

  envDefaultCenter =
    let
      explicitDefaultCenterKey = cfg.django.extraSettings.DEFAULT_CENTER_KEY or null;
      defaultCenterReference = lib.strings.trim (toString (
        cfg.django.extraSettings.DEFAULT_CENTER
    in
    if explicitDefaultCenterKey != null then
      explicitDefaultCenterKey
    else if defaultCenterReference == "" then
      "University Hospital Wuerzburg"
    else
      defaultCenterReference;
  exportFramesStorageRootDefault =
    config.roles.endoreg-client.paths.storagePersistingMountPoint;
  externalCleanupArchiveRootDefault =
    "${config.roles.endoreg-client.paths.storagePersistingMountPoint}/lx-annotate-archive";
  emergencyReliefArchiveRootDefault =
    "${config.roles.endoreg-client.paths.storagePersistingMountPoint}/lx-annotate-emergency-relief";
  emergencyReliefManifestDirDefault =
    "${emergencyReliefArchiveRootDefault}/manifests";
  emergencyReliefStagingDirDefault =
    "${emergencyReliefArchiveRootDefault}/.staging";
  emergencyReliefValidatedExportDirsDefault =
    [ "${runtimeDataRootPath}/export/frames" ];
  mkDjangoOptions = import ../../lib/django-options.nix { inherit lib; };
  dataRecoveryStateDir = "${runtimeRootPath}/state";
  dataRecoveryStateFile = "${dataRecoveryStateDir}/effective-data-dir.env";
  # TODO These NEED to be removed after data dir change.
  legacyRepoDataRootPath = "${repoDir}/data";
  legacyRepoMediaRootPath = "${repoDir}/media";
  processedReportDirName = "processed_reports_final";
  processedVideoDirName = "processed_videos_final";
  legacyDataProcessedReportDir = "${legacyRepoDataRootPath}/${processedReportDirName}";
  legacyDataProcessedVideoDir = "${legacyRepoDataRootPath}/${processedVideoDirName}";
  legacyMediaProcessedReportDir = "${legacyRepoMediaRootPath}/${processedReportDirName}";
  legacyMediaProcessedVideoDir = "${legacyRepoMediaRootPath}/${processedVideoDirName}";
  runtimeProcessedReportDir = "${runtimeStorageRootPath}/${processedReportDirName}";
  runtimeProcessedVideoDir = "${runtimeStorageRootPath}/${processedVideoDirName}";

  hubRootPath = "${runtimeDataRootPath}/hub";
  hubBackupRootPath = "${hubRootPath}/backup";
  hubBackupIncomingPath = "${hubBackupRootPath}/incoming";
  hubBackupSnapshotPath = "${hubBackupRootPath}/snapshots";
  hubBackupManifestPath = "${hubBackupRootPath}/manifests";

  lxAnnotateRuntime = {
    identities = {
      inherit
        adminName
        endoreg-service-user-name
        endoreg-service-user
        endoreg-service-user-home
        endoreg-service-group-name;
    };
    names = {
      inherit scriptName exportFramesScriptName;
    };
    source = {
      inherit gitURL repoDirName branchName;
    };
    paths = {
      inherit
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
        runtimeSapImportProcessedDirPath
        runtimeSapImportFailedDirPath
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
        viteSourcePath
        envDataDir
        envConfDir
        makeCacheDir
        envConfTemplateDir
        sslDir
        sslKeyPath
        sslCertPath
        envSystemdFilePath
        envAssetDir
        hubRootPath
        hubBackupRootPath
        hubBackupIncomingPath
        hubBackupSnapshotPath
        hubBackupManifestPath
        dataRecoveryStateDir
        dataRecoveryStateFile
        legacyRepoDataRootPath
        legacyRepoMediaRootPath
        legacyDataProcessedReportDir
        legacyDataProcessedVideoDir
        legacyMediaProcessedReportDir
        legacyMediaProcessedVideoDir
        runtimeProcessedReportDir
        runtimeProcessedVideoDir;
    };
    env = {
      inherit
        envNginxProtectedMediaUrl
        envDjangoModule
        envHttpProtocol
        envDjangoHost
        envDjangoPort
        envBaseUrl
        envStaticUrl
        envMediaUrl
        envRunVideoTests
        envSkipExpensiveTests
        envViteEnableDebug
        envAllowedHosts
        envCorsAllowedOrigins
        envAnnotateDjangoSettingsModule
        envDjangoEnv
        envCentralNodeFlag
        envDeploymentRole
        envDefaultCenter
        envIsCentralNode
        settingsProfile;
    };
    runtime = {
      inherit
        useWheelRuntime
        pythonInterpreter
        wheelFilePath
        packageVersion
        managedEncryptedDataServiceName
        encryptionServiceUnits
        encryptedDataMountOptions;
    };
    defaults = {
      inherit
        defaultSslCertificatePath
        defaultSslKeyPath
        exportFramesStorageRootDefault
        externalCleanupArchiveRootDefault
        emergencyReliefArchiveRootDefault
        emergencyReliefManifestDirDefault
        emergencyReliefStagingDirDefault
        emergencyReliefValidatedExportDirsDefault
        processedReportDirName
        processedVideoDirName;
    };
    helpers = {
      inherit makeAbsolute mkDjangoOptions;
    };
  };
in
{
  inherit cfg gs gsp sslCfg lxAnnotateRuntime;
}
