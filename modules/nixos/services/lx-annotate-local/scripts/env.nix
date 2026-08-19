{
  config,
  lib,
  pkgs,
  cfg,
  lxAnnotateRuntime,
  effectivePackageVersion ? lxAnnotateRuntime.runtime.packageVersion,
  packageStaticRoot ? lxAnnotateRuntime.paths.djangoStaticRootPath,
  runtimeLdLibraryPath ? "",
  ...
}:
let
  inherit (lib)
    concatStringsSep
    escapeShellArg
    mapAttrsToList
    optionalAttrs
    optionalString
    ;

  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-home
    ;
  inherit (runtime.paths)
    runtimeRootPath
    runtimeWatcherVideoDirPath
    runtimeWatcherReportDirPath
    runtimeWatcherPreanonymizedDirPath
    runtimeStreamableVideoRootPath
    runtimeStreamableVideoRawRootPath
    runtimeStreamableVideoProcessedRootPath
    runtimeWorkingDir
    envDataDir
    envConfDir
    envConfTemplateDir
    envAssetDir
    ;
  inherit (runtime.env)
    envAllowedHosts
    envBaseUrl
    envCentralNodeFlag
    envCorsAllowedOrigins
    envDefaultCenter
    envDeploymentRole
    envDjangoModule
    envDjangoPort
    envHttpProtocol
    envRunVideoTests
    envSkipExpensiveTests
    envViteEnableDebug
    ;

  boolString = value: if value then "true" else "false";
  streamableStorageProfile = "fs_encrypted_streaming";

  renderSystemdEnvLine =
    name: value:
    let
      escapedValue = lib.replaceStrings [ "\\" "\"" ] [ "\\\\" "\\\"" ] (toString value);
    in
    ''${name}="${escapedValue}"'';

  renderShellExport = name: value: "export ${name}=${escapeShellArg (toString value)}";
  renderShellExports = env: concatStringsSep "\n" (mapAttrsToList renderShellExport env);
in
rec {
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

  celeryDefaultQueueName = "default";
  celeryPipelineQueueName = "pipeline";
  celeryFrameExtractionQueueName = "frame_extraction";
  celeryFfmpegMediaQueueName = "ffmpeg_media";
  celeryInferenceQueueName = "inference";
  celeryTrainingQueueName = "model_training";
  celeryLlmInferenceQueueName = "llm_inference";
  celeryMaintenanceQueueName = "maintenance";
  celeryHubTransferQueueName = "hub_transfer";
  ffmpegTranscodeTimeoutSeconds = "86400";

  # This is the lx-annotate environment contract. Config modules, systemd
  # EnvironmentFiles, and shell wrappers render from this attrset.
  commonEnv = {
    HOME_DIR = endoreg-service-user-home;
    CONF_DIR = envConfDir;
    CONF_TEMPLATE_DIR = envConfTemplateDir;
    WORKING_DIR = runtimeWorkingDir;
    ASSET_DIR = envAssetDir;
    XDG_DATA_HOME = runtimeRootPath;
    LX_ANNOTATE_ENCRYPTED_DATA_DIR = envDataDir;
    WATCHER_VIDEO_DIR = runtimeWatcherVideoDirPath;
    WATCHER_REPORT_DIR = runtimeWatcherReportDirPath;
    WATCHER_PREANONYMIZED_DIR = runtimeWatcherPreanonymizedDirPath;
    DJANGO_HOST = "127.0.0.1";
    DJANGO_PORT = envDjangoPort;
    DJANGO_STATIC_ROOT = packageStaticRoot;
    ALLOWED_HOSTS = envAllowedHosts;
    DJANGO_ALLOWED_HOSTS = envAllowedHosts;
    DJANGO_CORS_ALLOWED_ORIGINS = envCorsAllowedOrigins;
    DJANGO_CSRF_TRUSTED_ORIGINS = envCorsAllowedOrigins;
    DJANGO_DB_ENGINE = "django.db.backends.postgresql";
    DJANGO_DB_NAME = cfg.database.name;
    DJANGO_DB_USER = cfg.database.user;
    DJANGO_DB_HOST = cfg.database.host;
    DJANGO_DB_PORT = toString cfg.database.port;
    DJANGO_DB_SSLMODE = cfg.database.sslMode;
    DB_PWD_FILE = "${envConfDir}/db_pwd";
    DJANGO_DB_PASSWORD_FILE = "${envConfDir}/db_pwd";
    DJANGO_SECRET_KEY_FILE = toString cfg.django.djangoSecretKeyFile;
    DJANGO_KEYCLOAK_CLIENT_SECRET_FILE = toString cfg.django.keycloakSecretFile;
    DJANGO_KEYCLOAK_CLIENT_ID = cfg.django.keycloakClientId;
    OIDC_RP_CLIENT_ID = cfg.django.keycloakClientId;
    DJANGO_MODULE = envDjangoModule;
    DJANGO_SETTINGS_MODULE_DEVELOPMENT = "lx_annotate.settings.settings_dev";
    CENTRAL_NODE = envCentralNodeFlag;
    BASE_URL = envBaseUrl;
    ENFORCE_AUTH = "1";
    EXEMPT_URLS = "^/accounts/login/$";
    LOGIN_URL = "/accounts/login/";
    VITE_ENABLE_DEBUG = envViteEnableDebug;
    HTTP_PROTOCOL = envHttpProtocol;
    TIME_ZONE = cfg.django.timeZone;
    RUN_VIDEO_TESTS = envRunVideoTests;
    SKIP_EXPENSIVE_TESTS = envSkipExpensiveTests;
    FFMPEG_TRANSCODE_TIMEOUT_SECONDS = ffmpegTranscodeTimeoutSeconds;
    MEDIA_OPERATION_STREAM_LEASE_SECONDS = "300";
    SERVE_WITH_NGINX = boolString cfg.runtime.streamableServing.nginxOffload;
    NGINX_PROTECTED_MEDIA_URL = cfg.runtime.streamableServing.protectedMediaUrl;
    LX_ANNOTATE_DEFAULT_CENTER = envDefaultCenter;
    LX_DTYPES_KB_REGISTRY = cfg.runtime.terminology.registryPath;
    LX_DTYPES_TERMINOLOGY_IMPORT_ROOT = cfg.runtime.terminology.importRoot;
    ENDOREG_DEPLOYMENT_ROLE = envDeploymentRole;
    ENDOREG_STORAGE_PROFILE = streamableStorageProfile;
    ENDOREG_HUB_MODE = boolString cfg.hub.enable;
    ENDOREG_ENABLE_HUB_TRANSFERS = boolString (cfg.hub.transferApi.enable || cfg.hub.outboundTransfer.enable);
    ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT = boolString cfg.hub.transferApi.requireSecureTransport;
    ENDOREG_HUB_TRANSFER_REQUIRE_MTLS = boolString cfg.hub.transferApi.requireMtls;
    ENDOREG_HUB_TRANSFER_MTLS_META_KEY = cfg.hub.transferApi.mtlsMetaKey;
    ENDOREG_HUB_TRANSFER_MTLS_META_VALUE = cfg.hub.transferApi.mtlsMetaValue;
    ENDOREG_HUB_TRANSFER_MAX_UPLOAD_BYTES = toString cfg.hub.transferApi.maxUploadBytes;
    LX_ANNOTATE_HUB_EXPORT_AUTO_QUEUE = boolString cfg.hub.outboundTransfer.enable;
    LX_ANNOTATE_HUB_EXPORT_REQUIRE_MTLS = boolString cfg.hub.outboundTransfer.requireMtls;
    LX_ANNOTATE_HUB_EXPORT_STALE_AFTER_SECONDS = toString cfg.hub.outboundTransfer.staleAfterSeconds;
    LX_ANNOTATE_HUB_EXPORT_MAX_RETRIES = toString cfg.hub.outboundTransfer.maxRetries;
    CELERY_BROKER_URL = celeryBrokerUrl;
    CELERY_DEFAULT_QUEUE = celeryDefaultQueueName;
    CELERY_PIPELINE_QUEUE = celeryPipelineQueueName;
    CELERY_FRAME_EXTRACTION_QUEUE = celeryFrameExtractionQueueName;
    CELERY_FFMPEG_MEDIA_QUEUE = celeryFfmpegMediaQueueName;
    CELERY_INFERENCE_QUEUE = celeryInferenceQueueName;
    CELERY_TRAINING_QUEUE = celeryTrainingQueueName;
    CELERY_LLM_INFERENCE_QUEUE = celeryLlmInferenceQueueName;
    CELERY_MAINTENANCE_QUEUE = celeryMaintenanceQueueName;
    CELERY_HUB_TRANSFER_QUEUE = celeryHubTransferQueueName;
    CELERY_FRAME_EXTRACTION_REQUIRE_SECURE_TRANSPORT = boolString cfg.runtime.celeryBroker.requireSecureTransport;
    CELERY_FFMPEG_MEDIA_REQUIRE_SECURE_TRANSPORT = boolString cfg.runtime.celeryBroker.requireSecureTransport;
    CELERY_BROKER_SECURE_TRANSPORT_CONFIRMED = boolString cfg.runtime.celeryBroker.secureTransportConfirmed;
    MODEL_TRAINING_JOB_MODE = "celery";
    MODEL_TRAINING_STAGING_ROOT = cfg.runtime.modelTrainingStagingRoot;
    VIDEO_POST_VALIDATION_JOB_MODE = "celery";
    VIDEO_TEMPORAL_INFERENCE_JOB_MODE = "celery";
    VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE = "stream";
    TESSDATA_PREFIX = cfg.runtime.tessdataPrefix;
    PYTORCH_ALLOC_CONF = cfg.runtime.pytorchAllocConf;
    LD_LIBRARY_PATH = runtimeLdLibraryPath;
    SSL_CERT_FILE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
    REQUESTS_CA_BUNDLE = "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt";
    LX_ANNOTATE_PACKAGE_VERSION = effectivePackageVersion;
    LX_ANNOTATE_STREAMABLE_VIDEO_ROOT = runtimeStreamableVideoRootPath;
    LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT = runtimeStreamableVideoRawRootPath;
    LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT = runtimeStreamableVideoProcessedRootPath;
  }
  // optionalAttrs (cfg.runtime.masterKeyFile != null) {
    LX_ANNOTATE_MASTER_KEY_FILE = toString cfg.runtime.masterKeyFile;
  }
  // optionalAttrs (cfg.hub.outboundTransfer.clientCertificateFile != null) {
    LX_ANNOTATE_HUB_EXPORT_CLIENT_CERT_FILE = toString cfg.hub.outboundTransfer.clientCertificateFile;
  }
  // optionalAttrs (cfg.hub.outboundTransfer.clientKeyFile != null) {
    LX_ANNOTATE_HUB_EXPORT_CLIENT_KEY_FILE = toString cfg.hub.outboundTransfer.clientKeyFile;
  }
  // optionalAttrs (cfg.hub.outboundTransfer.caFile != null) {
    LX_ANNOTATE_HUB_EXPORT_CA_FILE = toString cfg.hub.outboundTransfer.caFile;
  }
  // optionalAttrs (cfg.hub.outboundTransfer.sourceNodeSecretFile != null) {
    LX_ANNOTATE_HUB_SOURCE_NODE_SECRET_FILE = toString cfg.hub.outboundTransfer.sourceNodeSecretFile;
  }
  // optionalAttrs (cfg.hub.outboundTransfer.recipientPublicKeyFile != null) {
    LX_ANNOTATE_HUB_EXPORT_RECIPIENT_PUBLIC_KEY_FILE = toString cfg.hub.outboundTransfer.recipientPublicKeyFile;
  }
  // optionalAttrs (cfg.hub.transferApi.recipientPrivateKeyFiles != [ ]) {
    ENDOREG_HUB_TRANSFER_RECIPIENT_PRIVATE_KEY_FILES = lib.concatStringsSep "," cfg.hub.transferApi.recipientPrivateKeyFiles;
  }
  // cfg.runtime.extraEnvironment;

  commonSystemdEnvText = concatStringsSep "\n" (mapAttrsToList renderSystemdEnvLine commonEnv);
  commonShellExportText = renderShellExports commonEnv;

  celeryWorkerResourceEnv = {
    CELERY_LOG_LEVEL = "INFO";
    OMP_NUM_THREADS = "1";
    OPENBLAS_NUM_THREADS = "1";
    MKL_NUM_THREADS = "1";
    NUMEXPR_NUM_THREADS = "1";
    MALLOC_ARENA_MAX = "2";
  };
  celeryWorkerResourceShellExportText = renderShellExports celeryWorkerResourceEnv;

  llmInferenceWorkerEnv = {
    REPORT_LLM_JOB_MODE = "celery";
    LLM_ENABLED = "true";
    LLM_PROVIDER = "ollama";
    LLM_MODEL = "lx-gemma4-e2b-json";
    LLM_BASE_URL = "http://127.0.0.1:11434";
    LLM_TIMEOUT = "120";
  };

  lxAnnotateEnvHelpers = pkgs.writeShellScript "lx-annotate-env-helpers.sh" ''
    lx_annotate_export_base_env() {
      ${commonShellExportText}
      OIDC_CLIENT_SECRET_VALUE="$(tr -d '\n' < "${cfg.django.keycloakSecretFile}" 2>/dev/null || true)"
      export OIDC_RP_CLIENT_SECRET="$OIDC_CLIENT_SECRET_VALUE"
    }

    lx_annotate_export_storage_env() {
      local data_root="$1"
      export LX_ANNOTATE_ENCRYPTED_DATA_DIR="$data_root"
      export LX_ANNOTATE_STREAMABLE_VIDEO_ROOT="$data_root/storage/streamable_videos"
      export LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT="$data_root/storage/streamable_videos/raw"
      export LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT="$data_root/storage/streamable_videos/processed"
      export WATCHER_VIDEO_DIR="${runtimeWatcherVideoDirPath}"
      export WATCHER_REPORT_DIR="${runtimeWatcherReportDirPath}"
      export WATCHER_PREANONYMIZED_DIR="${runtimeWatcherPreanonymizedDirPath}"
    }

    lx_annotate_export_encryption_env() {
      ${optionalString (cfg.runtime.masterKeyFile != null) ''
        export LX_ANNOTATE_MASTER_KEY_FILE="${toString cfg.runtime.masterKeyFile}"
      ''}
      :
    }

    lx_annotate_export_django_paths_env() {
      export ASSET_DIR="${envAssetDir}"
    }

    lx_annotate_export_db_env() {
      local db_pwd
      db_pwd="$(tr -d '\n' < "${envConfDir}/db_pwd" 2>/dev/null || true)"
      export DJANGO_DB_ENGINE="django.db.backends.postgresql"
      export DJANGO_DB_NAME="${cfg.database.name}"
      export DJANGO_DB_USER="${cfg.database.user}"
      export DJANGO_DB_PASSWORD="$db_pwd"
      export DJANGO_DB_HOST="${cfg.database.host}"
      export DJANGO_DB_PORT="${toString cfg.database.port}"
      export DJANGO_DB_SSLMODE="${cfg.database.sslMode}"
    }

    lx_annotate_export_secret_key_env() {
      local django_secret_key
      django_secret_key="$(tr -d '\n' < "${cfg.django.djangoSecretKeyFile}" 2>/dev/null || true)"
      export DJANGO_SECRET_KEY="$django_secret_key"
    }

    lx_annotate_export_oidc_env() {
      local oidc_client_secret
      export OIDC_RP_CLIENT_ID="${cfg.django.keycloakClientId}"
      oidc_client_secret="$(tr -d '\n' < "${cfg.django.keycloakSecretFile}" 2>/dev/null || true)"
      export OIDC_RP_CLIENT_SECRET="$oidc_client_secret"
    }

    lx_annotate_export_wheel_service_env() {
      local data_root="$1"
      lx_annotate_export_base_env
      lx_annotate_export_storage_env "$data_root"
      lx_annotate_export_encryption_env
      lx_annotate_export_django_paths_env
      lx_annotate_export_db_env
      export DJANGO_DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD"
      lx_annotate_export_secret_key_env
      lx_annotate_export_oidc_env
      export WORKING_DIR="${runtimeWorkingDir}"
    }
  '';
}
