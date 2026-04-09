{
  config,
  lib,
  pkgs,
  ...
}@args:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.lxAnnotateLocal;
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;
  sslCfg = lib.attrByPath [ "services" "luxnix" "lxSsl" ] {
    enable = false;
    sslDir = "/var/lib/lx-annotate/ssl";
    certPath = "/var/lib/lx-annotate/ssl/lx-annotate-selfsigned.crt";
    keyPath = "/var/lib/lx-annotate/ssl/lx-annotate-selfsigned.key";
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
  endoreg-service-user-home = endoreg-service-user.home;
  endoreg-service-group-name = config.user.endoreg-service-user.group;
  runtimeRootPath = "/var/lib/lx-annotate";
  repoDir = "${endoreg-service-user-home}/${repoDirName}";
  repoStaticRootPath = "${repoDir}/staticfiles";
  runtimeDataRootPath = cfg.runtime.encryptedDataDir;
  # Canonical protected runtime layout:
  # - runtimeDataRootPath is the single protected root
  # - runtimeStorageRootPath is the managed storage subtree under that root
  # - runtimeIoImportRootPath is the intake/workflow subtree under that root
  #
  # Anything under the service-user home is only an access path or symlink and
  # must not be treated as an independent runtime root.
  runtimeStorageRootPath = "${runtimeDataRootPath}/storage";
  runtimeIoImportRootPath = "${runtimeDataRootPath}/import";
  runtimeStreamableVideoRootPath = "${runtimeStorageRootPath}/streamable_videos";
  runtimeStreamableVideoRawRootPath = "${runtimeStreamableVideoRootPath}/raw";
  runtimeStreamableVideoProcessedRootPath = "${runtimeStreamableVideoRootPath}/processed";
  envProtectedMediaRoot = runtimeStorageRootPath;
  envNginxProtectedMediaUrl = "/protected_media/";
  envStreamableVideoRoot = runtimeStreamableVideoRootPath;
  envStreamableVideoRawRoot = runtimeStreamableVideoRawRootPath;
  envStreamableVideoProcessedRoot = runtimeStreamableVideoProcessedRootPath;
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

  normalizeCenterKey =
    raw:
    let
      normalized =
        lib.strings.toLower
          (lib.replaceStrings
            [
              "Ä"
              "Ö"
              "Ü"
              "ä"
              "ö"
              "ü"
              "ß"
              " "
              "_"
              "/"
              "\\"
              "."
              ","
              ":"
              ";"
              "("
              ")"
              "["
              "]"
              "{"
              "}"
              "'"
              "\""
            ]
            [
              "ae"
              "oe"
              "ue"
              "ae"
              "oe"
              "ue"
              "ss"
              "-"
              "-"
              "-"
              "-"
              "-"
              "-"
              "-"
              "-"
              ""
              ""
              ""
              ""
              ""
              ""
              ""
              ""
            ]
            (lib.strings.trim (toString raw)));
      collapsed =
        lib.replaceStrings
          [ "---" "--" ]
          [ "-" "-" ]
          normalized;
      trimmed =
        lib.strings.removeSuffix "-"
          (lib.strings.removePrefix "-" collapsed);
    in
    if trimmed == "" then "university-hospital-wuerzburg" else trimmed;

  envDefaultCenter =
    cfg.django.extraSettings.DEFAULT_CENTER_KEY or (
      normalizeCenterKey (
        cfg.django.extraSettings.DEFAULT_CENTER or
        config.roles.endoreg-client.defaultCenter or
        "University Hospital Wuerzburg"
      )
    );
  exportFramesStorageRootDefault =
    config.roles.endoreg-client.paths.storagePersistingMountPoint;
  externalCleanupArchiveRootDefault =
    "${config.roles.endoreg-client.paths.storagePersistingMountPoint}/lx-annotate-archive";
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
  runtimeProcessedReportDir = "${runtimeDataRootPath}/${processedReportDirName}";
  runtimeProcessedVideoDir = "${runtimeDataRootPath}/${processedVideoDirName}";
  hubRootPath = "${runtimeDataRootPath}/hub";
  hubBackupRootPath = "${hubRootPath}/backup";
  hubBackupIncomingPath = "${hubBackupRootPath}/incoming";
  hubBackupSnapshotPath = "${hubBackupRootPath}/snapshots";
  hubBackupManifestPath = "${hubBackupRootPath}/manifests";

  shared = {
    inherit
      cfg
      gs
      gsp
      sslCfg
      defaultSslCertificatePath
      defaultSslKeyPath
      adminName
      scriptName
      exportFramesScriptName
      gitURL
      repoDirName
      branchName
      endoreg-service-user-name
      endoreg-service-user
      endoreg-service-user-home
      endoreg-service-group-name
      runtimeRootPath
      repoDir
      repoStaticRootPath
      runtimeDataRootPath
      runtimeStorageRootPath
      runtimeIoImportRootPath
      runtimeStreamableVideoRootPath
      runtimeStreamableVideoRawRootPath
      runtimeStreamableVideoProcessedRootPath
      runtimeStaticRootPath
      runtimeWheelRootPath
      runtimeWheelVenvPath
      useWheelRuntime
      runtimeWorkingDir
      staticRootPath
      djangoStaticRootPath
      viteSourcePath
      envDataDir
      envProtectedMediaRoot
      envNginxProtectedMediaUrl
      envStreamableVideoRoot
      envStreamableVideoRawRoot
      envStreamableVideoProcessedRoot
      envConfDir
      makeCacheDir
      envConfTemplateDir
      envDjangoModule
      envHttpProtocol
      envDjangoHost
      envDjangoPort
      envBaseUrl
      sslDir
      sslKeyPath
      sslCertPath
      envSystemdFilePath
      pythonInterpreter
      wheelFilePath
      managedEncryptedDataServiceName
      encryptionServiceUnits
      encryptedDataMountOptions
      makeAbsolute
      envAssetDir
      envStaticUrl
      envMediaUrl
      envRunVideoTests
      envSkipExpensiveTests
      envViteEnableDebug
      envAllowedHosts
      envCorsAllowedOrigins
      settingsProfile
      envIsCentralNode
      envAnnotateDjangoSettingsModule
      envDjangoEnv
      envCentralNodeFlag
      envDefaultCenter
      exportFramesStorageRootDefault
      externalCleanupArchiveRootDefault
      mkDjangoOptions
      legacyRepoDataRootPath
      legacyRepoMediaRootPath
      processedReportDirName
      processedVideoDirName
      legacyDataProcessedReportDir
      legacyDataProcessedVideoDir
      legacyMediaProcessedReportDir
      legacyMediaProcessedVideoDir
      runtimeProcessedReportDir
      runtimeProcessedVideoDir
      hubRootPath
      hubBackupRootPath
      hubBackupIncomingPath
      hubBackupSnapshotPath
      hubBackupManifestPath
      dataRecoveryStateDir
      dataRecoveryStateFile;
  };

  scriptExports = import ./scripts.nix (args // shared);
  moduleArgs = args // shared // scriptExports;
in
{
  imports = [
    (import ./options.nix moduleArgs)
    (import ./config.nix moduleArgs)
  ];
}
