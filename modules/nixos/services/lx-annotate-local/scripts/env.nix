args@{ lib, ... }:
with lib;
with lib.luxnix;
with args;
let
  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-home
    ;
  inherit (runtime.paths)
    runtimeRootPath
    repoDir
    runtimeStorageRootPath
    runtimeWatcherVideoDirPath
    runtimeWatcherReportDirPath
    runtimeWatcherPreanonymizedDirPath
    runtimeStreamableVideoRootPath
    runtimeStreamableVideoRawRootPath
    runtimeStreamableVideoProcessedRootPath
    runtimeWorkingDir
    djangoStaticRootPath
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
    envDjangoEnv
    envDjangoHost
    envDjangoModule
    envDjangoPort
    envHttpProtocol
    envMediaUrl
    envNginxProtectedMediaUrl
    envRunVideoTests
    envSkipExpensiveTests
    envStaticUrl
    envViteEnableDebug
    ;
  inherit (runtime.runtime) packageVersion;
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
  celeryMaintenanceQueueName = "maintenance";
  ffmpegTranscodeTimeoutSeconds = "86400";

  lxAnnotateEnvHelpers = pkgs.writeShellScript "lx-annotate-env-helpers.sh" ''
    lx_annotate_export_base_env() {
      export DJANGO_SECRET_KEY_FILE="${cfg.django.djangoSecretKeyFile}"
      export OIDC_RP_CLIENT_ID="${cfg.django.keycloakClientId}"
      OIDC_CLIENT_SECRET_VALUE="$(tr -d '\n' < "${cfg.django.keycloakSecretFile}" 2>/dev/null || true)"
      export OIDC_RP_CLIENT_SECRET="$OIDC_CLIENT_SECRET_VALUE"
      export CONF_DIR="${envConfDir}"
      export CONF_TEMPLATE_DIR="${envConfTemplateDir}"
      export WORKING_DIR="${repoDir}"
      export HOME_DIR="${endoreg-service-user-home}"
      export DB_PWD_FILE="${envConfDir}/db_pwd"
      export DJANGO_DB_PASSWORD_FILE="${envConfDir}/db_pwd"

      export DJANGO_MODULE="${envDjangoModule}"
      export DJANGO_SETTINGS_MODULE="lx_annotate.settings.settings_prod"
      export DJANGO_SETTINGS_MODULE_PRODUCTION="lx_annotate.settings.settings_prod"
      export DJANGO_SETTINGS_MODULE_DEVELOPMENT="lx_annotate.settings.settings_dev"
      export DJANGO_ENV="${envDjangoEnv}"
      export CENTRAL_NODE="${envCentralNodeFlag}"
      export HTTP_PROTOCOL="${envHttpProtocol}"
      export DJANGO_HOST="${envDjangoHost}"
      export DJANGO_PORT="${envDjangoPort}"
      export BASE_URL="${envBaseUrl}"
      export TIME_ZONE="${cfg.django.timeZone}"
      export RUN_VIDEO_TESTS="${envRunVideoTests}"
      export SKIP_EXPENSIVE_TESTS="${envSkipExpensiveTests}"
      export VITE_ENABLE_DEBUG="${envViteEnableDebug}"
      export SERVE_WITH_NGINX="true"
      export NGINX_PROTECTED_MEDIA_URL="${envNginxProtectedMediaUrl}"
      export LX_ANNOTATE_PACKAGE_VERSION="${packageVersion}"
      export ENDOREG_DEPLOYMENT_ROLE="${envDeploymentRole}"
      export ENDOREG_HUB_MODE="${if cfg.hub.enable then "true" else "false"}"
      export ENDOREG_ENABLE_HUB_TRANSFERS="${if cfg.hub.transferApi.enable then "true" else "false"}"
      export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT="${
        if cfg.hub.transferApi.requireSecureTransport then "true" else "false"
      }"
      export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS="${
        if cfg.hub.transferApi.requireMtls then "true" else "false"
      }"
      export ENDOREG_HUB_TRANSFER_MTLS_META_KEY="${cfg.hub.transferApi.mtlsMetaKey}"
      export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE="${cfg.hub.transferApi.mtlsMetaValue}"
      export CELERY_BROKER_URL="${celeryBrokerUrl}"
      export CELERY_DEFAULT_QUEUE="${celeryDefaultQueueName}"
      export CELERY_PIPELINE_QUEUE="${celeryPipelineQueueName}"
      export CELERY_FRAME_EXTRACTION_QUEUE="${celeryFrameExtractionQueueName}"
      export CELERY_FFMPEG_MEDIA_QUEUE="${celeryFfmpegMediaQueueName}"
      export CELERY_INFERENCE_QUEUE="${celeryInferenceQueueName}"
      export CELERY_TRAINING_QUEUE="${celeryTrainingQueueName}"
      export CELERY_MAINTENANCE_QUEUE="${celeryMaintenanceQueueName}"
      export CELERY_FRAME_EXTRACTION_REQUIRE_SECURE_TRANSPORT="${
        if cfg.runtime.celeryBroker.requireSecureTransport then "true" else "false"
      }"
      export CELERY_FFMPEG_MEDIA_REQUIRE_SECURE_TRANSPORT="${
        if cfg.runtime.celeryBroker.requireSecureTransport then "true" else "false"
      }"
      export CELERY_BROKER_SECURE_TRANSPORT_CONFIRMED="${
        if cfg.runtime.celeryBroker.secureTransportConfirmed then "true" else "false"
      }"
      export MODEL_TRAINING_JOB_MODE="celery"
      export MODEL_TRAINING_STAGING_ROOT="${cfg.runtime.modelTrainingStagingRoot}"
      export VIDEO_POST_VALIDATION_JOB_MODE="celery"
      export VIDEO_TEMPORAL_INFERENCE_JOB_MODE="celery"
      export VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE="stream"
      export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
      export REQUESTS_CA_BUNDLE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"

      export DJANGO_ALLOWED_HOSTS="${envAllowedHosts}"
      export ALLOWED_HOSTS="${envAllowedHosts}"
      export DJANGO_CORS_ALLOWED_ORIGINS="${envCorsAllowedOrigins}"
      export DJANGO_CSRF_TRUSTED_ORIGINS="${envCorsAllowedOrigins}"
      export FFMPEG_TRANSCODE_TIMEOUT_SECONDS="${ffmpegTranscodeTimeoutSeconds}"
    }

    lx_annotate_export_storage_env() {
      local data_root="$1"
      export DATA_DIR="$data_root"
      export LX_ANNOTATE_DATA_DIR="$data_root"
      export LX_ANNOTATE_ENCRYPTED_DATA_DIR="$data_root"
      export PROTECTED_MEDIA_ROOT="${runtimeStorageRootPath}"
      export STORAGE_DIR="$data_root/storage"
      export WATCHER_VIDEO_DIR="${runtimeWatcherVideoDirPath}"
      export WATCHER_REPORT_DIR="${runtimeWatcherReportDirPath}"
      export WATCHER_PREANONYMIZED_DIR="${runtimeWatcherPreanonymizedDirPath}"
      export LX_ANNOTATE_STREAMABLE_VIDEO_ROOT="${runtimeStreamableVideoRootPath}"
      export LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT="${runtimeStreamableVideoRawRootPath}"
      export LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT="${runtimeStreamableVideoProcessedRootPath}"
    }

    lx_annotate_export_encryption_env() {
      ${optionalString (cfg.runtime.masterKeyFile != null) ''
        export LX_ANNOTATE_MASTER_KEY_FILE="${toString cfg.runtime.masterKeyFile}"
      ''}
      :
    }

    lx_annotate_export_django_paths_env() {
      export STATIC_URL="${envStaticUrl}"
      export MEDIA_URL="${envMediaUrl}"
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
      export EXEMPT_URLS="^/accounts/login/$"
      export LOGIN_URL="/accounts/login/"
      export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
      export WORKING_DIR="${runtimeWorkingDir}"
      export HOME_DIR="${endoreg-service-user-home}"
      export XDG_DATA_HOME="${runtimeRootPath}"
      export LX_ANNOTATE_ENCRYPTED_DATA_DIR="$data_root"
      export LX_ANNOTATE_DATA_DIR="$data_root"
      export LX_ANNOTATE_DEFAULT_CENTER="${envDefaultCenter}"
      export TESSDATA_PREFIX="${cfg.runtime.tessdataPrefix}"
      export PYTORCH_ALLOC_CONF="${cfg.runtime.pytorchAllocConf}"
    }
  '';
}
