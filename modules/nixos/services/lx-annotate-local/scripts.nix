args@{ lib, ... }:
with lib;
with lib.luxnix;
with args;
let
  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-user-home
    endoreg-service-group-name;
  inherit (runtime.names) scriptName exportFramesScriptName;
  inherit (runtime.source) gitURL repoDirName branchName;
  inherit (runtime.paths)
    runtimeRootPath
    repoDir
    repoStaticRootPath
    runtimeStorageRootPath
    runtimeWatcherVideoDirPath
    runtimeWatcherReportDirPath
    runtimeWatcherPreanonymizedDirPath
    runtimeSapImportDirPath
    runtimeSapImportProcessedDirPath
    runtimeSapImportFailedDirPath
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
    makeCacheDir
    envConfTemplateDir
    envSystemdFilePath
    envAssetDir
    hubRootPath
    hubBackupRootPath
    hubBackupIncomingPath
    hubBackupSnapshotPath
    hubBackupManifestPath
    dataRecoveryStateDir
    dataRecoveryStateFile;
  inherit (runtime.env)
    envAllowedHosts
    envAnnotateDjangoSettingsModule
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
    envViteEnableDebug;
  inherit (runtime.runtime)
    useWheelRuntime
    pythonInterpreter
    wheelFilePath
    packageVersion
    encryptedDataMountOptions;
  inherit (runtime.defaults)
    exportFramesStorageRootDefault
    processedReportDirName
    processedVideoDirName;
  makeBin = "${pkgs.gnumake}/bin/make";
  celeryBrokerUrl =
    if cfg.runtime.externalServices.redisUrl != null then
      cfg.runtime.externalServices.redisUrl
    else
      lib.attrByPath
        [ "roles" "endoreg-client" "service" "extraEnvironment" "CELERY_BROKER_URL" ]
        "redis://localhost:6379/1"
        config;
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
      export ENDOREG_HUB_MODE="${
        if cfg.hub.enable then "true" else "false"
      }"
      export ENDOREG_ENABLE_HUB_TRANSFERS="${
        if cfg.hub.transferApi.enable then "true" else "false"
      }"
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
      ${
        optionalString (cfg.runtime.masterKeyFile != null) ''
          export LX_ANNOTATE_MASTER_KEY_FILE="${toString cfg.runtime.masterKeyFile}"
        ''
      }
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

  # Compat exports for lx-annotate/devenv.nix shellHook, which expects these vars.
  devenvSyncCompatExports = ''
    export SYNC_CMD="uv sync --active --extra dev --extra docs"
    export SYNC_STAMP=".devenv/state/.uv-sync.stamp"
    mkdir -p "$(dirname "$SYNC_STAMP")"
    if [ -f "uv.lock" ] && [ -f "pyproject.toml" ]; then
      export LOCK_HASH="$(${pkgs.coreutils}/bin/sha256sum uv.lock pyproject.toml 2>/dev/null | ${pkgs.coreutils}/bin/sha256sum | ${pkgs.coreutils}/bin/cut -d ' ' -f1)"
    else
      export LOCK_HASH=""
    fi
  '';

  alignEnvFileScript = pkgs.writeText "lx-annotate-align-env.py" ''
    import os
    from pathlib import Path

    env_path = Path(os.environ["LX_ANNOTATE_ENV_FILE"])
    desired_module = os.environ["DESIRED_SETTINGS_MODULE"]
    desired_env = os.environ["DESIRED_ENVIRONMENT"]

    if not env_path.exists():
        raise SystemExit(0)

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = []
    have_module = False
    have_env = False

    for line in lines:
        if line.startswith("DJANGO_SETTINGS_MODULE="):
            updated.append(f"DJANGO_SETTINGS_MODULE={desired_module}")
            have_module = True
        elif line.startswith("DJANGO_ENV="):
            updated.append(f"DJANGO_ENV={desired_env}")
            have_env = True
        else:
            updated.append(line)

    if not have_module:
        updated.append(f"DJANGO_SETTINGS_MODULE={desired_module}")

    if not have_env:
        updated.append(f"DJANGO_ENV={desired_env}")

    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
  '';

  viteManifestEntryScript = pkgs.writeText "lx-annotate-vite-manifest-entry.py" ''
    import json
    import sys

    manifest_path = sys.argv[1]
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise SystemExit(1)

    entry = data.get("src/main.ts", {}).get("file")
    if entry:
        print(entry)
        raise SystemExit(0)

    for value in data.values():
        if isinstance(value, dict):
            file_value = value.get("file")
            if file_value:
                print(file_value)
                raise SystemExit(0)

    raise SystemExit(1)
  '';


  syncScriptName = "lx-annotate-sync";
  prepareScriptName = "lx-annotate-prepare";
  buildScriptName = "lx-annotate-build";
  migrateScriptName = "lx-annotate-migrate";
  migrateVideoStreamableStorageScriptName = "lx-annotate-migrate-video-streamable-storage";
  emergencyStorageReliefScriptName = "runLxAnnotateEmergencyStorageRelief";
  startScriptName = "lx-annotate-start";
  bootstrapScriptName = "lx-annotate-bootstrap";
  masterKeyCheckScriptName = "runLocalMasterKeyCheck";
  acceptanceScriptName = "runLocalAcceptance";
  migrateWheelScriptName = "runLocalMigrate";
  loadBaseDataWheelScriptName = "runLocalLoadBaseData";
  wheelWebCommand = cfg.runtime.commands.web or "";
  wheelMigrateCommand = cfg.runtime.commands.migrate or "";
  wheelLoadBaseDataCommand = cfg.runtime.commands.loadBaseData or "";
  wheelFileWatcherCommand = cfg.runtime.commands.fileWatcher or "";
  wheelFileWatcherOnceCommand =
    if cfg.runtime.commands.fileWatcherOnce != null then
      cfg.runtime.commands.fileWatcherOnce
    else
      wheelFileWatcherCommand;
  wheelExportFramesCommand = cfg.runtime.commands.exportFrames or "";
  wheelCeleryWorkerCommand = cfg.runtime.commands.celeryWorker or "";
  wheelSapImportCommand = cfg.runtime.commands.sapImport or "";
  wheelMediaMigrationCommand = cfg.runtime.commands.mediaMigration or "";
  celeryDefaultQueueName = "default";
  celeryPipelineQueueName = "pipeline";
  celeryFrameExtractionQueueName = "frame_extraction";
  celeryFfmpegMediaQueueName = "ffmpeg_media";
  celeryInferenceQueueName = "inference";
  celeryTrainingQueueName = "model_training";
  celeryMaintenanceQueueName = "maintenance";
  ffmpegTranscodeTimeoutSeconds = "86400";
  emergencyStorageReliefConfig = pkgs.writeText "lx-annotate-emergency-storage-relief-config.json" (
    builtins.toJSON {
      archive_root = cfg.storageRelief.archiveDir;
      manifest_dir = cfg.storageRelief.manifestDir;
      staging_dir = cfg.storageRelief.stagingDir;
      external_mount_point = cfg.storageRelief.externalMountPoint;
      runtime_root = envDataDir;
      dry_run = cfg.storageRelief.dryRun;
      delete_after_verify = cfg.storageRelief.deleteAfterVerify;
      include_legacy_processed_duplicates = cfg.storageRelief.includeLegacyProcessedDuplicates;
      include_validated_export_bundles = cfg.storageRelief.includeValidatedExportBundles;
      validated_export_dirs = cfg.storageRelief.validatedExportDirs;
      validated_export_marker_names = cfg.storageRelief.validatedExportMarkerNames;
      legacy_duplicate_sources = [
        {
          kind = "report";
          source_root = cfg.dataCleanup.legacyProcessedReportDir;
          label = "legacy-data/${processedReportDirName}";
        }
        {
          kind = "video";
          source_root = cfg.dataCleanup.legacyProcessedVideoDir;
          label = "legacy-data/${processedVideoDirName}";
        }
        {
          kind = "report";
          source_root = cfg.dataCleanup.legacyMediaProcessedReportDir;
          label = "legacy-media/${processedReportDirName}";
        }
        {
          kind = "video";
          source_root = cfg.dataCleanup.legacyMediaProcessedVideoDir;
          label = "legacy-media/${processedVideoDirName}";
        }
      ];
    }
  );
  emergencyStorageReliefHelper = pkgs.writeText "lx-annotate-emergency-storage-relief.py" ''
    from __future__ import annotations

    import argparse
    import json
    import os
    import sys
    from datetime import datetime, timezone
    from enum import Enum
    from pathlib import Path
    from typing import Any


    class ReliefResourceKind(str, Enum):
        VIDEO = "video"
        REPORT = "report"


    def parse_resource_kind(value: object) -> ReliefResourceKind | None:
        try:
            return ReliefResourceKind(str(value).lower())
        except ValueError:
            return None


    def emit(event: str, **payload: object) -> None:
        record = {"event": event, **payload}
        print(json.dumps(record, sort_keys=True), flush=True)


    def load_config(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("storage relief config must be a JSON object")
        return data


    def setup_django() -> None:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lx_annotate.settings.settings_prod")
        import django

        django.setup()


    def state_is_processed_anonymized(state: object | None) -> bool:
        if state is None:
            return False
        return bool(
            getattr(state, "anonymization_validated", False)
            or getattr(state, "sensitive_meta_processed", False)
            or getattr(state, "anonymized", False)
        )


    def state_is_validated(state: object | None) -> bool:
        return bool(state is not None and getattr(state, "anonymization_validated", False))


    def field_name_keys(field_name: str) -> set[str]:
        normalized = field_name.strip("/")
        keys = {normalized, Path(normalized).name}
        parts = normalized.split("/", 1)
        if len(parts) == 2:
            keys.add(parts[1])
        return {key for key in keys if key}


    def archive_destination(root: Path, category: str, label: str, rel_path: Path, content_hash: str) -> Path:
        destination = root / category / label / rel_path
        if not destination.exists():
            return destination
        return destination.with_name(f"{destination.name}.{content_hash[:16]}")


    def staging_destination(staging_root: Path, archive_root: Path, destination: Path, content_hash: str) -> Path:
        final_rel_path = destination.resolve().relative_to(archive_root.resolve())
        staged = staging_root / final_rel_path
        return staged.with_name(f"{staged.name}.{os.getpid()}.{content_hash[:16]}.staging")


    def ensure_archive_path(path: Path, archive_root: Path) -> None:
        resolved_path = path.resolve()
        resolved_archive = archive_root.resolve()
        if resolved_path == resolved_archive or resolved_archive in resolved_path.parents:
            return
        raise ValueError(f"refusing to write outside archive root: {path}")


    def resource_identifier(kind: ReliefResourceKind, obj: object) -> str:
        return f'{kind.value}:{getattr(obj, "pk", "")}'


    def build_eligible_resources() -> dict[str, dict[str, dict[str, Any]]]:
        from endoreg_db.models import RawPdfFile, VideoFile

        resources: dict[str, dict[str, dict[str, Any]]] = {
            kind.value: {} for kind in ReliefResourceKind
        }

        videos = (
            VideoFile.objects.select_related("state")
            .exclude(processed_file="")
            .exclude(processed_file__isnull=True)
            .order_by("pk")
        )
        for video in videos.iterator():
            field = getattr(video, "processed_file", None)
            field_name = str(getattr(field, "name", "") or "")
            if not field_name or not state_is_processed_anonymized(getattr(video, "state", None)):
                continue
            record = {
                "kind": ReliefResourceKind.VIDEO.value,
                "object": video,
                "field_file": field,
                "content_hash": getattr(video, "processed_video_hash", None) or None,
                "validated": state_is_validated(getattr(video, "state", None)),
                "identifier": resource_identifier(ReliefResourceKind.VIDEO, video),
            }
            for key in field_name_keys(field_name):
                resources[ReliefResourceKind.VIDEO.value][key] = record

        reports = (
            RawPdfFile.objects.select_related("state")
            .exclude(processed_file="")
            .exclude(processed_file__isnull=True)
            .order_by("pk")
        )
        for report in reports.iterator():
            field = getattr(report, "processed_file", None)
            field_name = str(getattr(field, "name", "") or "")
            if not field_name or not state_is_processed_anonymized(getattr(report, "state", None)):
                continue
            record = {
                "kind": ReliefResourceKind.REPORT.value,
                "object": report,
                "field_file": field,
                "content_hash": None,
                "validated": state_is_validated(getattr(report, "state", None)),
                "identifier": resource_identifier(ReliefResourceKind.REPORT, report),
            }
            for key in field_name_keys(field_name):
                resources[ReliefResourceKind.REPORT.value][key] = record

        return resources


    def get_record_hash(record: dict[str, Any]) -> str:
        cached = record.get("content_hash")
        if cached:
            return str(cached)
        from endoreg_db.utils.file_operations import sha256_file

        digest = sha256_file(record["field_file"])
        record["content_hash"] = digest
        return digest


    def copy_verify_delete(
        *,
        source: Path,
        destination: Path,
        archive_root: Path,
        staging_root: Path,
        dry_run: bool,
        delete_after_verify: bool,
        expected_hash: str | None,
    ) -> dict[str, Any]:
        from endoreg_db.utils.file_operations import (
            atomic_copy_file,
            atomic_move_file,
            safe_unlink_file,
            sha256_file,
        )

        ensure_archive_path(destination, archive_root)
        ensure_archive_path(staging_root, archive_root)
        size_bytes = source.stat().st_size
        source_hash = sha256_file(source)
        if expected_hash is not None and source_hash != expected_hash:
            return {
                "status": "skipped",
                "reason": "source hash does not match eligible database payload",
                "source": str(source),
                "source_hash": source_hash,
                "expected_hash": expected_hash,
            }

        if dry_run:
            return {
                "status": "planned",
                "source": str(source),
                "destination": str(destination),
                "source_hash": source_hash,
                "bytes": size_bytes,
            }

        staged = staging_destination(staging_root, archive_root, destination, source_hash)
        ensure_archive_path(staged, archive_root)
        try:
            atomic_copy_file(
                source=source,
                destination=staged,
                preserve_metadata=True,
                file_mode=0o640,
                dir_mode=0o750,
            )
            staged_hash = sha256_file(staged)
            if staged_hash != source_hash:
                raise RuntimeError(
                    f"staging hash verification failed for {source}: {staged_hash} != {source_hash}"
                )
            atomic_move_file(
                source=staged,
                destination=destination,
                file_mode=0o640,
                dir_mode=0o750,
            )
        except Exception:
            if staged.exists():
                safe_unlink_file(staged, missing_ok=True)
            raise

        destination_hash = sha256_file(destination)
        if destination_hash != source_hash:
            raise RuntimeError(
                f"archive hash verification failed for {source}: {destination_hash} != {source_hash}"
            )

        deleted = False
        if delete_after_verify:
            safe_unlink_file(source, missing_ok=False)
            deleted = True

        return {
            "status": "archived",
            "source": str(source),
            "destination": str(destination),
            "staging": str(staged),
            "source_hash": source_hash,
            "bytes": size_bytes,
            "deleted": deleted,
        }


    def archive_legacy_duplicates(
        *,
        config: dict[str, Any],
        resources: dict[str, dict[str, dict[str, Any]]],
        archive_root: Path,
        staging_root: Path,
        dry_run: bool,
        delete_after_verify: bool,
        ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for source_config in config.get("legacy_duplicate_sources", []):
            kind = parse_resource_kind(source_config["kind"])
            if kind is None:
                emit(
                    "lx_annotate_storage_relief_skip",
                    reason="unknown legacy duplicate source kind",
                    kind=str(source_config["kind"]),
                )
                continue
            source_root = Path(str(source_config["source_root"]))
            label = str(source_config["label"]).strip("/")
            if not source_root.is_dir():
                emit(
                    "lx_annotate_storage_relief_skip",
                    reason="legacy source missing",
                    source_root=str(source_root),
                    kind=kind.value,
                )
                continue

            for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
                rel_path = source.relative_to(source_root)
                keys = {rel_path.as_posix(), source.name}
                record = next(
                    (
                        resources.get(kind.value, {}).get(key)
                        for key in keys
                        if resources.get(kind.value, {}).get(key)
                    ),
                    None,
                )
                if record is None:
                    items.append(
                        {
                            "status": "skipped",
                            "reason": "no eligible database payload",
                            "kind": kind.value,
                            "source": str(source),
                        }
                    )
                    continue

                expected_hash = get_record_hash(record)
                source_hash = None
                destination = archive_destination(
                    archive_root,
                    "duplicates",
                    label,
                    rel_path,
                    expected_hash,
                )
                result = copy_verify_delete(
                    source=source,
                    destination=destination,
                    archive_root=archive_root,
                    staging_root=staging_root,
                    dry_run=dry_run,
                    delete_after_verify=delete_after_verify,
                    expected_hash=expected_hash,
                )
                result.update(
                    {
                        "kind": kind.value,
                        "category": "legacy_processed_duplicate",
                        "resource": record["identifier"],
                        "label": label,
                    }
                )
                if result.get("source_hash"):
                    source_hash = result["source_hash"]
                emit("lx_annotate_storage_relief_item", **result)
                items.append(result)
                if source_hash and result["status"] == "skipped":
                    continue
        return items


    def marker_payload(marker: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
        except Exception as exc:
            emit(
                "lx_annotate_storage_relief_skip",
                reason="invalid export marker json",
                marker=str(marker),
                detail=str(exc),
            )
            return None
        if not isinstance(payload, dict) or payload.get("validated") is not True:
            return None
        return payload


    def marker_resources(payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw_resources = payload.get("resources")
        if raw_resources is None:
            raw_resources = [
                {
                    "kind": payload.get("resource_kind"),
                    "id": payload.get("resource_id"),
                }
            ]
        if not isinstance(raw_resources, list):
            return []
        return [item for item in raw_resources if isinstance(item, dict)]


    def resource_is_validated(resource: dict[str, Any]) -> bool:
        from endoreg_db.models import RawPdfFile, VideoFile

        kind = parse_resource_kind(resource.get("kind") or resource.get("resource_kind"))
        pk = resource.get("id", resource.get("pk", resource.get("resource_id")))
        if kind is None or pk in {None, ""}:
            return False
        if kind is ReliefResourceKind.VIDEO:
            model = VideoFile
        elif kind is ReliefResourceKind.REPORT:
            model = RawPdfFile
        else:
            raise ValueError(f"unhandled relief resource kind: {kind.value}")
        obj = model.objects.select_related("state").filter(pk=pk).first()
        return bool(obj is not None and state_is_validated(getattr(obj, "state", None)))


    def find_validated_bundle_roots(export_dir: Path, marker_names: list[str]) -> list[tuple[Path, Path]]:
        bundles: list[tuple[Path, Path]] = []
        if not export_dir.is_dir():
            return bundles
        for root, dirs, files in os.walk(export_dir):
            root_path = Path(root)
            marker_name = next((name for name in marker_names if name in files), None)
            if marker_name is None:
                continue
            bundles.append((root_path, root_path / marker_name))
            dirs[:] = []
        return bundles


    def archive_validated_export_bundles(
        *,
        config: dict[str, Any],
        archive_root: Path,
        staging_root: Path,
        dry_run: bool,
        delete_after_verify: bool,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        marker_names = [str(name) for name in config.get("validated_export_marker_names", [])]
        for export_dir_value in config.get("validated_export_dirs", []):
            export_dir = Path(str(export_dir_value))
            for bundle_root, marker in find_validated_bundle_roots(export_dir, marker_names):
                payload = marker_payload(marker)
                if payload is None:
                    continue
                resources = marker_resources(payload)
                if not resources or not all(resource_is_validated(resource) for resource in resources):
                    emit(
                        "lx_annotate_storage_relief_skip",
                        reason="export bundle resources are not validated",
                        bundle_root=str(bundle_root),
                        marker=str(marker),
                    )
                    continue

                bundle_label = bundle_root.relative_to(export_dir).as_posix()
                if bundle_label == ".":
                    bundle_label = export_dir.name
                for source in sorted(path for path in bundle_root.rglob("*") if path.is_file()):
                    rel_path = source.relative_to(bundle_root)
                    destination = archive_destination(
                        archive_root,
                        "validated-export-bundles",
                        bundle_label,
                        rel_path,
                        datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                    )
                    result = copy_verify_delete(
                        source=source,
                        destination=destination,
                        archive_root=archive_root,
                        staging_root=staging_root,
                        dry_run=dry_run,
                        delete_after_verify=delete_after_verify,
                        expected_hash=None,
                    )
                    result.update(
                        {
                            "category": "validated_export_bundle",
                            "bundle_root": str(bundle_root),
                            "marker": str(marker),
                        }
                    )
                    emit("lx_annotate_storage_relief_item", **result)
                    items.append(result)
        return items


    def write_manifest(
        manifest_dir: Path,
        archive_root: Path,
        staging_root: Path,
        dry_run: bool,
        items: list[dict[str, Any]],
    ) -> Path:
        from endoreg_db.utils.file_operations import atomic_write_file, ensure_directory

        ensure_directory(manifest_dir, dir_mode=0o750)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        manifest = {
            "schema": "lx_annotate_emergency_storage_relief.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "archive_root": str(archive_root),
            "staging_root": str(staging_root),
            "dry_run": dry_run,
            "items": items,
            "archived_count": sum(1 for item in items if item.get("status") == "archived"),
            "planned_count": sum(1 for item in items if item.get("status") == "planned"),
            "skipped_count": sum(1 for item in items if item.get("status") == "skipped"),
            "freed_bytes": sum(int(item.get("bytes", 0)) for item in items if item.get("deleted") is True),
        }
        payload = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        destination = manifest_dir / f"{timestamp}.json"
        atomic_write_file(
            destination=destination,
            content=[payload],
            required_bytes=len(payload),
            file_mode=0o640,
            dir_mode=0o750,
        )
        return destination


    def main() -> int:
        parser = argparse.ArgumentParser()
        parser.add_argument("--config", required=True)
        args = parser.parse_args()

        config = load_config(Path(args.config))
        archive_root = Path(str(config["archive_root"]))
        manifest_dir = Path(str(config["manifest_dir"]))
        staging_root = Path(str(config["staging_dir"]))
        dry_run = bool(config.get("dry_run", False))
        delete_after_verify = bool(config.get("delete_after_verify", True))

        setup_django()
        items: list[dict[str, Any]] = []
        resources = build_eligible_resources()

        emit(
            "lx_annotate_storage_relief_start",
            archive_root=str(archive_root),
            staging_root=str(staging_root),
            dry_run=dry_run,
            eligible_videos=len(resources["video"]),
            eligible_reports=len(resources["report"]),
        )

        if config.get("include_legacy_processed_duplicates", True):
            items.extend(
                archive_legacy_duplicates(
                    config=config,
                    resources=resources,
                    archive_root=archive_root,
                    staging_root=staging_root,
                    dry_run=dry_run,
                    delete_after_verify=delete_after_verify,
                )
            )

        if config.get("include_validated_export_bundles", True):
            items.extend(
                archive_validated_export_bundles(
                    config=config,
                    archive_root=archive_root,
                    staging_root=staging_root,
                    dry_run=dry_run,
                    delete_after_verify=delete_after_verify,
                )
            )

        manifest_path = write_manifest(manifest_dir, archive_root, staging_root, dry_run, items)
        emit(
            "lx_annotate_storage_relief_complete",
            manifest=str(manifest_path),
            archived_count=sum(1 for item in items if item.get("status") == "archived"),
            planned_count=sum(1 for item in items if item.get("status") == "planned"),
            skipped_count=sum(1 for item in items if item.get("status") == "skipped"),
            freed_bytes=sum(int(item.get("bytes", 0)) for item in items if item.get("deleted") is True),
        )
        return 0


    if __name__ == "__main__":
        try:
            raise SystemExit(main())
        except Exception as exc:
            emit("lx_annotate_storage_relief_error", detail=str(exc))
            raise
  '';

  lxAnnotateRuntimeLib = pkgs.writeShellScript "lx-annotate-runtime-lib.sh" ''
        set -euo pipefail

        log() {
          printf '%s\n' "$*"
        }

        warn() {
          printf 'WARNING: %s\n' "$*" >&2
        }

        die() {
          printf 'ERROR: %s\n' "$*" >&2
          exit 1
        }

        lx_annotate_export_runtime_env() {
          source "${lxAnnotateEnvHelpers}"
          lx_annotate_export_base_env
          lx_annotate_export_storage_env "${envDataDir}"
          lx_annotate_export_encryption_env
          lx_annotate_export_django_paths_env
          lx_annotate_export_db_env
          export DJANGO_DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD"
          lx_annotate_export_secret_key_env
          lx_annotate_export_oidc_env
          export EXEMPT_URLS="^/accounts/login/$"
          export LOGIN_URL="/accounts/login/"
          export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
          export LX_ANNOTATE_DEFAULT_CENTER="${envDefaultCenter}"
          export LX_ANNOTATE_ENV_FILE="${repoDir}/.env"
        }

        lx_annotate_activate_runtime() {
          cd "${repoDir}"
          if command -v direnv >/dev/null 2>&1; then
            direnv allow || true
          fi
          ${devenvSyncCompatExports}
          if [ -d "${repoDir}/.devenv/profile/bin" ]; then
            export PATH="${repoDir}/.devenv/profile/bin:$PATH"
          fi
          if [ -f ".devenv/state/venv/bin/activate" ]; then
            # shellcheck disable=SC1091
            source .devenv/state/venv/bin/activate
          elif [ -f ".venv/bin/activate" ]; then
            # shellcheck disable=SC1091
            source .venv/bin/activate
          fi
          if [ -n "''${LOCK_HASH:-}" ] && command -v uv >/dev/null 2>&1; then
            previousLockHash="$(cat "$SYNC_STAMP" 2>/dev/null || true)"
            if [ ! -x "${repoDir}/.devenv/state/venv/bin/python" ] || [ "$LOCK_HASH" != "$previousLockHash" ]; then
              log "uv deps changed or venv missing -> syncing..."
              eval "$SYNC_CMD" || warn "uv sync failed; continuing with existing environment."
              printf '%s\n' "$LOCK_HASH" > "$SYNC_STAMP"
            else
              log "uv deps unchanged -> skipping sync."
            fi
          fi
        }

        ensure_wheel_runtime_installed() {
          local wheel_hash=""
          local wheelhouse_path="${optionalString (cfg.runtime.wheelhousePath != null) (toString cfg.runtime.wheelhousePath)}"
          local wheelhouse_hash="no-wheelhouse"
          local pip_install_args=""
          local wheel_install_stamp_file="${runtimeRootPath}/.wheel-install.sha256"
          local wheel_install_lock_file="${runtimeRootPath}/.wheel-install.lock"
          local installed_hash=""
          local canonical_wheel_name=""
          local staged_wheel_path=""
          local install_hash=""
          local wheel_installer_revision="stop-workers-before-wheel-install-v1"
          local venv_created="false"

          if [ -z "${wheelFilePath}" ]; then
            die "services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set in wheel mode."
          fi

          install -d -m 0750 "${runtimeRootPath}" "${runtimeWheelRootPath}" "${runtimeWheelVenvPath}" "${envConfDir}" "${envDataDir}"
          install -d -m 0775 "${runtimeStaticRootPath}" "${runtimeStaticRootPath}/.vite"

          wheel_hash="$(${pkgs.coreutils}/bin/sha256sum "${wheelFilePath}" | ${pkgs.coreutils}/bin/cut -d ' ' -f1)"
          canonical_wheel_name="$(${pkgs.coreutils}/bin/basename "${wheelFilePath}" | ${pkgs.gnused}/bin/sed -E 's/^[a-z0-9]{32}-//')"
          staged_wheel_path="${runtimeRootPath}/$canonical_wheel_name"

          if [ -n "$wheelhouse_path" ]; then
            if [ ! -d "$wheelhouse_path" ]; then
              die "Configured runtime.wheelhousePath does not exist: $wheelhouse_path"
            fi
            wheelhouse_hash="$((
              ${pkgs.findutils}/bin/find "$wheelhouse_path" -maxdepth 1 -type f             \( -name '*.whl' -o -name '*.tar.gz' -o -name '*.zip' \) -print0           | ${pkgs.coreutils}/bin/sort -z           | ${pkgs.findutils}/bin/xargs -0 -r ${pkgs.coreutils}/bin/sha256sum
            ) | ${pkgs.coreutils}/bin/sha256sum | ${pkgs.coreutils}/bin/cut -d ' ' -f1)"
            pip_install_args="--no-index --find-links $wheelhouse_path"
          fi

          install_hash="$(
            printf '%s
    %s
    %s
    %s
    '           "$wheel_hash"           "$wheelhouse_hash"           "${pythonInterpreter}"           "$wheel_installer_revision"         | ${pkgs.coreutils}/bin/sha256sum         | ${pkgs.coreutils}/bin/cut -d ' ' -f1
          )"

          exec 9>"$wheel_install_lock_file"
          ${pkgs.util-linux}/bin/flock 9

          if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
            "${pythonInterpreter}" -m venv "${runtimeWheelVenvPath}"
            venv_created="true"
          fi

          installed_hash="$(${pkgs.coreutils}/bin/cat "$wheel_install_stamp_file" 2>/dev/null || true)"

          if [ "$venv_created" = "true" ] || [ "$install_hash" != "$installed_hash" ]; then
            ${pkgs.coreutils}/bin/install -m 0640 "${wheelFilePath}" "$staged_wheel_path"
            # shellcheck disable=SC2086
            "${runtimeWheelVenvPath}/bin/pip" install --upgrade --force-reinstall $pip_install_args "$staged_wheel_path"
            printf '%s
    ' "$install_hash" > "$wheel_install_stamp_file"
            chmod 0640 "$wheel_install_stamp_file" 2>/dev/null || true
          fi

          ${pkgs.util-linux}/bin/flock -u 9
          exec 9>&-

          export PATH="${runtimeWheelVenvPath}/bin:$PATH"
          export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
          export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
          export WHEEL_INSTALL_HASH="$install_hash"
        }

        run_installed_django_command() {
          local python_bin="$1"
          shift
          "$python_bin" -m django "$@" --settings=lx_annotate.settings.settings_prod
        }

        repair_known_wheel_schema_drift() {
          "${runtimeWheelVenvPath}/bin/python" - <<'PY'
    import django
    from django.apps import apps
    from django.db import connection

    django.setup()

    try:
        model = apps.get_model("endoreg_db", "VideoState")
    except LookupError:
        raise SystemExit(0)

    field_names = [
        "outside_segments_removed",
        "ready_for_export",
        "ready_for_export_at",
        "ready_for_export_by",
        "processed_file_sha256",
    ]
    model_fields = {field.name: field for field in model._meta.local_fields}
    field_names = [name for name in field_names if name in model_fields]

    if not field_names:
        raise SystemExit(0)

    with connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in connection.introspection.get_table_description(
                cursor,
                model._meta.db_table,
            )
        }

    missing = [name for name in field_names if name not in existing_columns]
    if not missing:
        raise SystemExit(0)

    with connection.schema_editor() as schema_editor:
        for name in missing:
            schema_editor.add_field(model, model_fields[name])

    print("Repaired known VideoState schema drift: " + ", ".join(missing))
    PY
        }

        ensure_runtime_static_root() {
          install -d -m 0775 "${staticRootPath}"
          install -d -m 0775 "${staticRootPath}/.vite"
          chown -R "${endoreg-service-user-name}:${endoreg-service-group-name}" "${staticRootPath}"

          if [ -L "${repoStaticRootPath}" ]; then
            ln -sfn ${staticRootPath} "${repoStaticRootPath}"
            return 0
          fi

          if [ -d "${repoStaticRootPath}" ]; then
            if find "${repoStaticRootPath}" -mindepth 1 -maxdepth 1 -print -quit >/dev/null 2>&1; then
              cp -a "${repoStaticRootPath}/." "${staticRootPath}/"
            fi
            rm -rf "${repoStaticRootPath}"
          elif [ -e "${repoStaticRootPath}" ]; then
            rm -f "${repoStaticRootPath}"
          fi

          ln -sfn ${staticRootPath} "${repoStaticRootPath}"
        }

        normalize_runtime_static_root_permissions() {
          if [ ! -d "${staticRootPath}" ]; then
            return 0
          fi

          chown -R "${endoreg-service-user-name}:${endoreg-service-group-name}" "${staticRootPath}"
          find "${staticRootPath}" -type d -exec chmod 0755 {} +
          find "${staticRootPath}" -type f -exec chmod 0644 {} +
        }

        emit_common_systemd_env() {
          cat <<EOF
    HOME_DIR=${endoreg-service-user-home}
    DATA_DIR=${envDataDir}
    LX_ANNOTATE_ENCRYPTED_DATA_DIR=${envDataDir}
    LX_ANNOTATE_DATA_DIR=${envDataDir}
    PROTECTED_MEDIA_ROOT=${runtimeStorageRootPath}
    CONF_DIR=${envConfDir}
    CONF_TEMPLATE_DIR=${envConfTemplateDir}
    WORKING_DIR=${repoDir}
    DJANGO_STATIC_ROOT=${djangoStaticRootPath}
    STORAGE_DIR=${envDataDir}/storage
    LX_ANNOTATE_STREAMABLE_VIDEO_ROOT=${runtimeStreamableVideoRootPath}
    LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT=${runtimeStreamableVideoRawRootPath}
    LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT=${runtimeStreamableVideoProcessedRootPath}
    SERVE_WITH_NGINX=true
    NGINX_PROTECTED_MEDIA_URL=${envNginxProtectedMediaUrl}
    LX_ANNOTATE_PACKAGE_VERSION=${packageVersion}
    ENDOREG_DEPLOYMENT_ROLE=${envDeploymentRole}
    ENDOREG_HUB_MODE=${if cfg.hub.enable then "true" else "false"}
    ENDOREG_ENABLE_HUB_TRANSFERS=${if cfg.hub.transferApi.enable then "true" else "false"}
    ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=${if cfg.hub.transferApi.requireSecureTransport then "true" else "false"}
    ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=${if cfg.hub.transferApi.requireMtls then "true" else "false"}
    ENDOREG_HUB_TRANSFER_MTLS_META_KEY=${cfg.hub.transferApi.mtlsMetaKey}
    ENDOREG_HUB_TRANSFER_MTLS_META_VALUE=${cfg.hub.transferApi.mtlsMetaValue}
    CELERY_BROKER_URL=${celeryBrokerUrl}
    CELERY_DEFAULT_QUEUE=${celeryDefaultQueueName}
    CELERY_PIPELINE_QUEUE=${celeryPipelineQueueName}
    CELERY_FRAME_EXTRACTION_QUEUE=${celeryFrameExtractionQueueName}
    CELERY_FFMPEG_MEDIA_QUEUE=${celeryFfmpegMediaQueueName}
    CELERY_INFERENCE_QUEUE=${celeryInferenceQueueName}
    CELERY_TRAINING_QUEUE=${celeryTrainingQueueName}
    CELERY_MAINTENANCE_QUEUE=${celeryMaintenanceQueueName}
    CELERY_FRAME_EXTRACTION_REQUIRE_SECURE_TRANSPORT=${if cfg.runtime.celeryBroker.requireSecureTransport then "true" else "false"}
    CELERY_FFMPEG_MEDIA_REQUIRE_SECURE_TRANSPORT=${if cfg.runtime.celeryBroker.requireSecureTransport then "true" else "false"}
    CELERY_BROKER_SECURE_TRANSPORT_CONFIRMED=${if cfg.runtime.celeryBroker.secureTransportConfirmed then "true" else "false"}
    MODEL_TRAINING_JOB_MODE=celery
    MODEL_TRAINING_STAGING_ROOT=${cfg.runtime.modelTrainingStagingRoot}
    VIDEO_POST_VALIDATION_JOB_MODE=celery
    VIDEO_TEMPORAL_INFERENCE_JOB_MODE=celery
    VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE=stream
    SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
    REQUESTS_CA_BUNDLE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
    DEBUG=False
    DJANGO_DEBUG=False
    VITE_ENABLE_DEBUG=${envViteEnableDebug}
    HTTP_PROTOCOL=${envHttpProtocol}
    DJANGO_HOST=${envDjangoHost}
    DJANGO_PORT=${envDjangoPort}
    BASE_URL=${envBaseUrl}
    DJANGO_ALLOWED_HOSTS=${envAllowedHosts}
    ALLOWED_HOSTS=${envAllowedHosts}
    DJANGO_CORS_ALLOWED_ORIGINS=${envCorsAllowedOrigins}
    DJANGO_CSRF_TRUSTED_ORIGINS=${envCorsAllowedOrigins}
    FFMPEG_TRANSCODE_TIMEOUT_SECONDS=${ffmpegTranscodeTimeoutSeconds}


    EOF
        }

        write_systemd_env_file() {
          install -d -m 0750 "${runtimeRootPath}" "${envDataDir}"
          emit_common_systemd_env > "${envSystemdFilePath}"
          # Legacy compatibility: older app builds read .env.systemd from the data root.
          # Keep both paths aligned to avoid startup failures on stale/corrupted legacy files.
          emit_common_systemd_env > "${envDataDir}/.env.systemd"
          chmod 0640 "${envSystemdFilePath}" "${envDataDir}/.env.systemd"
        }

        write_wheel_systemd_env_file() {
          write_systemd_env_file
          cat >> "${envSystemdFilePath}" <<EOF
    DJANGO_SETTINGS_MODULE=lx_annotate.settings.settings_prod
    DJANGO_SETTINGS_MODULE_PRODUCTION=lx_annotate.settings.settings_prod
    DJANGO_ENV=production
    XDG_DATA_HOME=${runtimeRootPath}
    TESSDATA_PREFIX=${cfg.runtime.tessdataPrefix}
    PYTORCH_ALLOC_CONF=${cfg.runtime.pytorchAllocConf}
    ${optionalString (cfg.runtime.masterKeyFile != null) "LX_ANNOTATE_MASTER_KEY_FILE=${toString cfg.runtime.masterKeyFile}"}
    EOF
          cp -f "${envSystemdFilePath}" "${envDataDir}/.env.systemd"
          chmod 0640 "${envSystemdFilePath}" "${envDataDir}/.env.systemd"
        }

        write_secretspec_config() {
          local config_dir="${endoreg-service-user-home}/config"
          local secretspec_config_dir="${endoreg-service-user-home}/lx-annotate/.config/secretspec"

          mkdir -p "$config_dir" "$secretspec_config_dir"
          cat > "$secretspec_config_dir/config.toml" <<EOF
    [defaults]
    provider = "env"
    profile = "production"
    EOF
        }

        align_repo_env_file() {
          if [ -f "${repoDir}/.env" ]; then
            log "Aligning .env with production settings module"
            export DESIRED_SETTINGS_MODULE="${envAnnotateDjangoSettingsModule}"
            export DESIRED_ENVIRONMENT="${envDjangoEnv}"
            "${pkgs.python3}/bin/python3" "${alignEnvFileScript}"
          else
            warn ".env not found"
          fi
        }

        vite_manifest_points_to_existing_asset() {
          local manifest_path="$1"
          local main_entry_file=""
          if [ ! -f "$manifest_path" ]; then
            return 1
          fi
          main_entry_file="$("${pkgs.python3}/bin/python3" "${viteManifestEntryScript}" "$manifest_path" 2>/dev/null || true)"
          if [ -z "$main_entry_file" ]; then
            return 1
          fi
          [ -f "${djangoStaticRootPath}/$main_entry_file" ]
        }

        ensure_runtime_vite_manifest() {
          local manifest_path="$1"
          local static_root="$2"
          local main_js="$static_root/main.js"
          local main_css="$static_root/main.css"

          if [ ! -f "$main_js" ]; then
            return 0
          fi

          if [ -s "$manifest_path" ] && "${pkgs.python3}/bin/python3" - "$manifest_path" >/dev/null 2>&1 <<'PY'
    import json
    import pathlib
    import sys

    manifest_path = pathlib.Path(sys.argv[1])
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = data.get("src/main.ts")
    if isinstance(entry, dict) and entry.get("file"):
        raise SystemExit(0)
    raise SystemExit(1)
    PY
          then
            return 0
          fi

          install -d -m 0775 "$(${pkgs.coreutils}/bin/dirname "$manifest_path")"
          "${pkgs.python3}/bin/python3" - "$manifest_path" "$main_js" "$main_css" <<'PY'
    import json
    from pathlib import Path
    import sys

    manifest_path = Path(sys.argv[1])
    main_js = Path(sys.argv[2])
    main_css = Path(sys.argv[3])

    entry = {
        "file": main_js.name,
        "isEntry": True,
    }
    if main_css.exists():
        entry["css"] = [main_css.name]

    manifest_path.write_text(
        json.dumps({"src/main.ts": entry}, indent=2) + "\n",
        encoding="utf-8",
    )
    PY
        }

        backup_git_state() {
          local backup_root="${runtimeRootPath}/git-backups"
          local timestamp=""

          install -d -m 0750 "$backup_root"
          timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%dT%H%M%S)"

          if ! git diff --quiet --ignore-submodules=all; then
            git diff --binary > "$backup_root/''${timestamp}-tracked.patch" || true
          fi

          if [ -n "$(git ls-files --others --exclude-standard)" ]; then
            git ls-files --others --exclude-standard -z \
              | ${pkgs.findutils}/bin/xargs -0 -r ${pkgs.gnutar}/bin/tar -czf "$backup_root/''${timestamp}-untracked.tgz" --
          fi

          warn "Backed up local git state into $backup_root before destructive sync."
        }

        last_known_good_revision_file() {
          printf '%s\n' "${runtimeRootPath}/last-known-good.revision"
        }

        current_revision_or_unknown() {
          git rev-parse --verify HEAD 2>/dev/null || echo unknown
        }


        restore_last_known_good_checkout() {
          local revision_file=""
          local fallback_revision=""

          revision_file="$(last_known_good_revision_file)"
          if [ ! -f "$revision_file" ]; then
            warn "No last-known-good revision file found at $revision_file"
            return 1
          fi

          fallback_revision="$(tr -d '\n' < "$revision_file" 2>/dev/null || true)"
          if [ -z "$fallback_revision" ]; then
            warn "Last-known-good revision file is empty: $revision_file"
            return 1
          fi

          cd "${repoDir}"
          if ! git rev-parse --verify "$fallback_revision^{commit}" >/dev/null 2>&1; then
            warn "Last-known-good revision is not available locally: $fallback_revision"
            return 1
          fi

          warn "Restoring last-known-good checkout: $fallback_revision"
          backup_git_state
          git checkout --force "$fallback_revision"
          log "Restored last-known-good revision $fallback_revision"
          return 0
        }

        guarded_hard_reset() {
          local target_ref="$1"
          : "''${LX_ANNOTATE_ALLOW_DESTRUCTIVE_GIT_RESET:=${if cfg.source.updateOnBoot then "true" else "false"}}"
          warn "Destructive git reset requested to $target_ref."
          backup_git_state
          if [ "$LX_ANNOTATE_ALLOW_DESTRUCTIVE_GIT_RESET" != "true" ]; then
            die "Refusing destructive git reset because LX_ANNOTATE_ALLOW_DESTRUCTIVE_GIT_RESET is not true."
          fi
          git reset --hard "$target_ref"
        }

        ensure_clean_latest_checkout() {
          local branch="${branchName}"
          local remote="origin"
          local remote_head=""
          local local_head=""

          log "Ensuring checkout matches $remote/$branch..."
          git fetch "$remote" "$branch" || die "Failed to fetch $remote/$branch."

          if ! git show-ref --verify --quiet "refs/remotes/$remote/$branch"; then
            die "Remote branch $remote/$branch not found."
          fi

          if git show-ref --verify --quiet "refs/heads/$branch"; then
            git checkout "$branch"
          else
            git checkout -B "$branch" "$remote/$branch"
          fi

          remote_head="$(git rev-parse --verify "$remote/$branch" 2>/dev/null || true)"
          local_head="$(git rev-parse --verify HEAD 2>/dev/null || true)"
          if [ -z "$remote_head" ] || [ -z "$local_head" ]; then
            die "Unable to resolve git revision for checkout verification."
          fi

          if [ "$local_head" != "$remote_head" ]; then
            guarded_hard_reset "$remote_head"
          fi

          if [ -d ".make-cache" ]; then
            git clean -fd -- ".make-cache" >/dev/null 2>&1 || true
          fi

          local_head="$(git rev-parse --verify HEAD 2>/dev/null || true)"
          if [ "$local_head" != "$remote_head" ]; then
            die "Checkout still differs from $remote/$branch after sync."
          fi

          log "Repository synced to commit $local_head on branch $branch."
        }

        sync_repo_checkout() {
          log "Starting LxAnnotate repository sync."
          log "Repository: ${gitURL}"
          log "Branch: ${branchName}"

          if [ -d "${repoDir}" ] && [ ! -d "${repoDir}/.git" ]; then
            warn "Target directory exists but is not a git repository. Removing it."
            rm -rf "${repoDir}"
          fi
          if [ ! -d "${repoDir}" ]; then
            log "Cloning repository..."
            git clone -b "${branchName}" "${gitURL}" "${repoDir}"
          fi

          cd "${repoDir}"
          if command -v direnv >/dev/null 2>&1; then
            direnv allow || true
          fi
          mkdir -p "${envConfDir}" "${makeCacheDir}"

          if [ -f "Makefile" ]; then
            log "Using Makefile repository sync targets..."
            if git ls-files --error-unmatch ".make-cache/migrations.sha256" >/dev/null 2>&1; then
              if ! git diff --quiet -- ".make-cache/migrations.sha256"; then
                log "Resetting tracked cache file .make-cache/migrations.sha256 before repository sync."
                git show "HEAD:.make-cache/migrations.sha256" > ".make-cache/migrations.sha256" || true
              fi
            fi
            ${
              if cfg.source.updateOnBoot then
                ''
                  "${makeBin}" REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" BRANCH="${branchName}" GIT_URL="${gitURL}" REMOTE="origin" update || {
                    warn "Repository update failed; continuing with current checkout."
                  }
                  ensure_clean_latest_checkout
                ''
              else
                ''
                  "${makeBin}" REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" BRANCH="${branchName}" GIT_URL="${gitURL}" REMOTE="origin" setup
                ''
            }
          else
            log "Makefile not found, using legacy git workflow."
            ${
              if cfg.source.updateOnBoot then
                ''
                  git fetch origin "${branchName}" || die "Failed to fetch from origin."
                ''
              else
                ''
                  log "Repository update disabled"
                ''
            }

            if git show-ref --verify --quiet "refs/heads/${branchName}"; then
              git checkout "${branchName}" || die "Checkout failed."
            elif git show-ref --verify --quiet "refs/remotes/origin/${branchName}"; then
              git checkout -b "${branchName}" "origin/${branchName}" || die "Tracking branch failed."
            else
              die "Branch ${branchName} does not exist."
            fi

            ${
              if cfg.source.updateOnBoot then
                ''
                  git pull origin "${branchName}" || {
                    warn "Failed to pull, falling back to guarded reset."
                    guarded_hard_reset "origin/${branchName}"
                  }
                  ensure_clean_latest_checkout
                ''
              else
                ""
            }
          fi
        }
  '';

  lxAnnotateSyncScript = pkgs.writeShellScriptBin "${syncScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"
    sync_repo_checkout
  '';

  lxAnnotatePrepareScript = pkgs.writeShellScriptBin "${prepareScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"
    mkdir -p "${envConfDir}" "${envDataDir}"
    ensure_runtime_static_root || warn "Failed to prepare runtime static root."
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime
    write_secretspec_config || warn "Failed to write secretspec config."
    printf '%s\n' "${envDjangoEnv}" > "${repoDir}/.mode"
    chmod 600 "${repoDir}/.mode" 2>/dev/null || true
    align_repo_env_file || warn "Failed to align repository .env file."
    write_systemd_env_file || warn "Failed to write systemd environment file."
  '';

  lxAnnotateBuildScript = pkgs.writeShellScriptBin "${buildScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime

    if [ "''${DJANGO_STATIC_ROOT%/}" = "${viteSourcePath}" ]; then
      warn "DJANGO_STATIC_ROOT points to Vite source assets (${viteSourcePath}); skipping frontend build enforcement."
      exit 0
    fi

    log "Building frontend assets into ${djangoStaticRootPath}..."
    if command -v devenv >/dev/null 2>&1; then
      devenv shell -- vue-build || warn "Frontend build failed; validating existing Vite manifest."
    else
      warn "devenv is not available; skipping frontend build."
    fi
    normalize_runtime_static_root_permissions || warn "Failed to normalize runtime static root permissions."
    if ! vite_manifest_points_to_existing_asset "${djangoStaticRootPath}/.vite/manifest.json"; then
      warn "Vite manifest is missing/invalid after frontend build preparation. Continuing with backend startup."
    fi
  '';

  lxAnnotateMigrateScript = pkgs.writeShellScriptBin "${migrateScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime

    log "Running database migrations..."
    python manage.py migrate --noinput

    bootstrap_stamp_file="${envConfDir}/.bootstrap-revision"
    current_revision="$(git rev-parse --verify HEAD 2>/dev/null || echo unknown)"
    last_bootstrap_revision="$(cat "$bootstrap_stamp_file" 2>/dev/null || true)"


    python manage.py load_base_db_data || warn "load_base_db_data failed; continuing after successful migrations."


    if [ "$current_revision" != "$last_bootstrap_revision" ]; then
      printf '%s\n' "$current_revision" > "$bootstrap_stamp_file"
      chmod 600 "$bootstrap_stamp_file" 2>/dev/null || true
    fi
  '';

  lxAnnotateMigrateVideoStreamableStorageScript = pkgs.writeShellScriptBin "${migrateVideoStreamableStorageScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"

    if [ "${if useWheelRuntime then "true" else "false"}" = "true" ] && [ -z ${lib.escapeShellArg wheelMediaMigrationCommand} ]; then
      echo "ERROR: runtime.commands.mediaMigration must be set when wheel mode enables media migration."
      exit 1
    fi

    media_storage_args=("$@")
    if [ "$#" -eq 0 ]; then
      media_storage_args=(
        --apply
        --repeat-until-empty
        --include-raw
        --include-processed
        --include-reports
        --include-streamable
        --json
      )
    fi

    log "Migrating canonical media into encrypted storage and syncing streamable artifacts..."
    if [ "${if useWheelRuntime then "true" else "false"}" = "true" ]; then
      source "${lxAnnotateEnvHelpers}"
      lx_annotate_export_wheel_service_env "${envDataDir}"
      ensure_wheel_runtime_installed
      media_migration_command=${lib.escapeShellArg wheelMediaMigrationCommand}
      printf -v media_storage_args_shell '%q ' "''${media_storage_args[@]}"
      exec "${pkgs.bash}/bin/bash" -lc "$media_migration_command $media_storage_args_shell"
    else
      lx_annotate_export_runtime_env
      lx_annotate_activate_runtime
      python manage.py migrate_media_storage "''${media_storage_args[@]}"
    fi
  '';

  lxAnnotateBootstrapScript = pkgs.writeShellScriptBin "${bootstrapScriptName}" ''
    set -euo pipefail

    source "${lxAnnotateRuntimeLib}"

    run_stage() {
      local label="$1"
      local script_path="$2"
      log "Running bootstrap stage: $label"
      "$script_path"
    }

    finalize_fallback_prepare() {
      log "Preparing restored last-known-good checkout for service start."
      "${lxAnnotatePrepareScript}/bin/${prepareScriptName}"
      if ! vite_manifest_points_to_existing_asset "${djangoStaticRootPath}/.vite/manifest.json"; then
        warn "Fallback checkout restored, but static assets are not usable. Continuing with backend startup."
      fi
    }

    if \
      run_stage "sync" "${lxAnnotateSyncScript}/bin/${syncScriptName}" && \
      run_stage "prepare" "${lxAnnotatePrepareScript}/bin/${prepareScriptName}" && \
      run_stage "build" "${lxAnnotateBuildScript}/bin/${buildScriptName}" && \
      run_stage "migrate" "${lxAnnotateMigrateScript}/bin/${migrateScriptName}"; then
      exit 0
    fi

    warn "Bootstrap pipeline failed; attempting fallback to last-known-good checkout."
    if restore_last_known_good_checkout; then
      finalize_fallback_prepare
      warn "Fallback checkout restored successfully. Continuing service start."
      exit 0
    fi

    die "Bootstrap failed and no usable last-known-good checkout could be restored."
  '';

  runLocalLxAnnotateStartScript = pkgs.writeShellScriptBin "${startScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime
    if ! vite_manifest_points_to_existing_asset "${djangoStaticRootPath}/.vite/manifest.json"; then
      warn "Vite manifest is missing/invalid before server start. Continuing with backend startup."
    fi
    log "Starting Django server..."
    if command -v devenv >/dev/null 2>&1; then
      exec devenv shell -- bash -c "run-server"
    fi
    die "run-server command not found in current environment."
  '';

  runLocalLxAnnotateScript = pkgs.writeShellScriptBin "${scriptName}" ''
        set -euo pipefail
        "${lxAnnotateSyncScript}/bin/${syncScriptName}"
        "${lxAnnotatePrepareScript}/bin/${prepareScriptName}"
        "${lxAnnotateBuildScript}/bin/${buildScriptName}"
        "${lxAnnotateMigrateScript}/bin/${migrateScriptName}"
        exec "${runLocalLxAnnotateStartScript}/bin/${startScriptName}"
      '';
  runLocalMigrateWheelScript = pkgs.writeShellScriptBin "${migrateWheelScriptName}" ''
        set -euo pipefail

        if [ -z ${lib.escapeShellArg wheelMigrateCommand} ]; then
          echo "ERROR: runtime.commands.migrate must be set when wheel mode uses the migration service."
          exit 1
        fi

        source "${lxAnnotateRuntimeLib}"
        source "${lxAnnotateEnvHelpers}"
        lx_annotate_export_wheel_service_env "${envDataDir}"
        ensure_wheel_runtime_installed
        write_wheel_systemd_env_file
        export PATH="${runtimeWheelVenvPath}/bin:$PATH"
        export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
        export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"

        log "Applying Django migrations for wheel runtime."
        "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg wheelMigrateCommand}
        repair_known_wheel_schema_drift
      '';
  runLocalLoadBaseDataWheelScript = pkgs.writeShellScriptBin "${loadBaseDataWheelScriptName}" ''
        set -euo pipefail

        if [ -z ${lib.escapeShellArg wheelLoadBaseDataCommand} ]; then
          echo "ERROR: runtime.commands.loadBaseData must be set when wheel mode uses the base-data service."
          exit 1
        fi

        source "${lxAnnotateRuntimeLib}"
        source "${lxAnnotateEnvHelpers}"
        lx_annotate_export_wheel_service_env "${envDataDir}"
        ensure_wheel_runtime_installed
        install_hash="$WHEEL_INSTALL_HASH"
        write_wheel_systemd_env_file
        export PATH="${runtimeWheelVenvPath}/bin:$PATH"
        export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
        export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"

        bootstrap_stamp_file="${envConfDir}/.bootstrap-wheel"
        last_bootstrap_hash="$(${pkgs.coreutils}/bin/cat "$bootstrap_stamp_file" 2>/dev/null || true)"

        if [ "$install_hash" = "$last_bootstrap_hash" ]; then
          log "Wheel runtime unchanged; skipping base data load."
          exit 0
        fi

        log "Wheel runtime changed; loading base data."
        if "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg wheelLoadBaseDataCommand}; then
          printf '%s\n' "$install_hash" > "$bootstrap_stamp_file"
          chmod 600 "$bootstrap_stamp_file" 2>/dev/null || true
        else
          warn "load_base_db_data failed; continuing after successful migrations."
        fi
      '';
  runLocalLxAnnotateWheelScript = pkgs.writeShellScriptBin "${scriptName}" ''
        set -euo pipefail

        if [ -z ${lib.escapeShellArg wheelWebCommand} ]; then
          echo "ERROR: runtime.commands.web must be set when wheel mode runs the web service."
          exit 1
        fi

        source "${lxAnnotateRuntimeLib}"
        source "${lxAnnotateEnvHelpers}"
        lx_annotate_export_wheel_service_env "${envDataDir}"
        ensure_wheel_runtime_installed

        write_wheel_systemd_env_file

        package_static_dir="$("${runtimeWheelVenvPath}/bin/python" - <<'PY'
    from pathlib import Path
    import lx_annotate

    package_root = Path(lx_annotate.__file__).resolve().parent
    for candidate in (package_root / "staticfiles", package_root / "static"):
        if candidate.exists():
            print(candidate)
            break
    PY
    )"

        if [ -z "$package_static_dir" ] || [ ! -d "$package_static_dir" ]; then
          echo "ERROR: No packaged static assets found in installed wheel."
          exit 1
        fi

        ${pkgs.rsync}/bin/rsync -a --delete "$package_static_dir"/ "${runtimeStaticRootPath}/"
        ensure_runtime_vite_manifest "${runtimeStaticRootPath}/.vite/manifest.json" "${runtimeStaticRootPath}"
        if ! vite_manifest_points_to_existing_asset "${runtimeStaticRootPath}/.vite/manifest.json"; then
          echo "ERROR: Installed wheel does not provide a usable Vite manifest for src/main.ts."
          exit 1
        fi
        if [ -e "${djangoStaticRootPath}" ] && [ ! -L "${djangoStaticRootPath}" ]; then
          rm -rf "${djangoStaticRootPath}"
        fi
        ln -sfn ${runtimeStaticRootPath} "${djangoStaticRootPath}"
        ${pkgs.coreutils}/bin/chown -R "${endoreg-service-user-name}:${endoreg-service-group-name}" "${runtimeStaticRootPath}"
        ${pkgs.findutils}/bin/find "${runtimeStaticRootPath}" -type d -exec ${pkgs.coreutils}/bin/chmod 0755 {} +
        ${pkgs.findutils}/bin/find "${runtimeStaticRootPath}" -type f -exec ${pkgs.coreutils}/bin/chmod 0644 {} +

        export PATH="${runtimeWheelVenvPath}/bin:$PATH"
        export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
        export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
        exec "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg wheelWebCommand}
  '';
  runLocalAcceptanceScript = pkgs.writeShellScriptBin "${acceptanceScriptName}" ''
    set -euo pipefail

    source "${lxAnnotateRuntimeLib}"
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime

    cd "${repoDir}"
    export MEDIA_URL="${envNginxProtectedMediaUrl}"
    mkdir -p "${runtimeStorageRootPath}" "${runtimeStreamableVideoRootPath}" "${runtimeStreamableVideoRawRootPath}" "${runtimeStreamableVideoProcessedRootPath}"

    python manage.py check --fail-level CRITICAL
    python manage.py verify_encrypted_storage
    ${pkgs.curl}/bin/curl --fail --silent --show-error --insecure \
      --resolve "${cfg.django.hostname}:443:127.0.0.1" \
      "https://${cfg.django.hostname}/static/.vite/manifest.json" >/dev/null

    log "lx-annotate acceptance checks passed."
  '';
  watcherScriptName = "runLocalFileWatcher";
  runLocalFileWatcherScript = pkgs.writeShellScriptBin "${watcherScriptName}" ''
    set -euo pipefail

    # 1. Go to the repo (Cloned by the main boot service)
    cd "${repoDir}"

    # 2. Re-Export ALL necessary Environment Variables
    # (Note: We skip git clone/pull because the boot service handles that)

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export LX_ANNOTATE_FILEWATCHER_ARGS="--process-existing-once"
    ${devenvSyncCompatExports}

    # 4. Start the Watcher inside the devenv shell
    echo "📁 Starting File Watcher..."

    if [ -f Makefile ] && command -v devenv >/dev/null 2>&1; then
      exec "${makeBin}" REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" start-watcher
    fi

    exec devenv shell run-filewatcher
  '';
  runLocalFileWatcherWheelScript = pkgs.writeShellScriptBin "${watcherScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelFileWatcherOnceCommand} ]; then
      echo "ERROR: runtime.commands.fileWatcherOnce or runtime.commands.fileWatcher must be set when wheel mode enables the watcher service."
      exit 1
    fi

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export LX_ANNOTATE_FILEWATCHER_ARGS="--process-existing-once"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    exec "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg wheelFileWatcherOnceCommand}
  '';
  celeryWorkerScriptName = "runLocalCeleryWorker";
  celeryPipelineWorkerScriptName = "runLocalCeleryPipelineWorker";
  celeryFrameExtractionWorkerScriptName = "runLocalCeleryFrameExtractionWorker";
  celeryFfmpegWorkerScriptName = "runLocalCeleryFfmpegWorker";
  celeryInferenceWorkerScriptName = "runLocalCeleryInferenceWorker";
  celeryTrainingWorkerScriptName = "runLocalCeleryTrainingWorker";
  runLocalCeleryWorkerScript = pkgs.writeShellScriptBin "${celeryWorkerScriptName}" ''
    set -euo pipefail

    cd "${repoDir}"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    ${devenvSyncCompatExports}

    celery_worker_args=(
      -A lx_annotate.celery:app
      worker
      --loglevel=INFO
      --hostname="maintenance@%h"
      --queues="${celeryMaintenanceQueueName},${celeryDefaultQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.maintenance.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.maintenance.maxTasksPerChild}"
    )

    exec devenv shell -- celery "''${celery_worker_args[@]}"
  '';
  runLocalCeleryWorkerWheelScript = pkgs.writeShellScriptBin "${celeryWorkerScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
      echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
    celery_worker_args=(
      --hostname="maintenance@%h"
      --queues="${celeryMaintenanceQueueName},${celeryDefaultQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.maintenance.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.maintenance.maxTasksPerChild}"
    )
    printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
    exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
  '';
  runLocalCeleryPipelineWorkerScript = pkgs.writeShellScriptBin "${celeryPipelineWorkerScriptName}" ''
    set -euo pipefail

    cd "${repoDir}"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    ${devenvSyncCompatExports}

    celery_worker_args=(
      -A lx_annotate.celery:app
      worker
      --loglevel=INFO
      --hostname="pipeline@%h"
      --queues="${celeryPipelineQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.pipeline.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.pipeline.maxTasksPerChild}"
    )

    exec devenv shell -- celery "''${celery_worker_args[@]}"
  '';
  runLocalCeleryPipelineWorkerWheelScript = pkgs.writeShellScriptBin "${celeryPipelineWorkerScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
      echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
    celery_worker_args=(
      --hostname="pipeline@%h"
      --queues="${celeryPipelineQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.pipeline.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.pipeline.maxTasksPerChild}"
    )
    printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
    exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
  '';
  runLocalCeleryFrameExtractionWorkerScript = pkgs.writeShellScriptBin "${celeryFrameExtractionWorkerScriptName}" ''
    set -euo pipefail

    cd "${repoDir}"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    ${devenvSyncCompatExports}

    celery_worker_args=(
      -A lx_annotate.celery:app
      worker
      --loglevel=INFO
      --hostname="frame-extraction@%h"
      --queues="${celeryFrameExtractionQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.frameExtraction.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.frameExtraction.maxTasksPerChild}"
    )

    exec devenv shell -- celery "''${celery_worker_args[@]}"
  '';
  runLocalCeleryFrameExtractionWorkerWheelScript = pkgs.writeShellScriptBin "${celeryFrameExtractionWorkerScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
      echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
    celery_worker_args=(
      --hostname="frame-extraction@%h"
      --queues="${celeryFrameExtractionQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.frameExtraction.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.frameExtraction.maxTasksPerChild}"
    )
    printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
    exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
  '';
  runLocalCeleryFfmpegWorkerScript = pkgs.writeShellScriptBin "${celeryFfmpegWorkerScriptName}" ''
    set -euo pipefail

    cd "${repoDir}"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    ${devenvSyncCompatExports}

    celery_worker_args=(
      -A lx_annotate.celery:app
      worker
      --loglevel=INFO
      --hostname="ffmpeg-media@%h"
      --queues="${celeryFfmpegMediaQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.ffmpeg.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.ffmpeg.maxTasksPerChild}"
    )

    exec devenv shell -- celery "''${celery_worker_args[@]}"
  '';
  runLocalCeleryFfmpegWorkerWheelScript = pkgs.writeShellScriptBin "${celeryFfmpegWorkerScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
      echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
    celery_worker_args=(
      --hostname="ffmpeg-media@%h"
      --queues="${celeryFfmpegMediaQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.ffmpeg.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.ffmpeg.maxTasksPerChild}"
    )
    printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
    exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
  '';
  runLocalCeleryInferenceWorkerScript = pkgs.writeShellScriptBin "${celeryInferenceWorkerScriptName}" ''
    set -euo pipefail

    cd "${repoDir}"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export VIDEO_TEMPORAL_INFERENCE_JOB_MODE="celery"
    export VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE="stream"
    ${optionalString (cfg.runtime.inferenceWorker.cudaVisibleDevices != null) ''
      export CUDA_VISIBLE_DEVICES="${cfg.runtime.inferenceWorker.cudaVisibleDevices}"
    ''}
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    ${devenvSyncCompatExports}

    celery_worker_args=(
      -A lx_annotate.celery:app
      worker
      --loglevel=INFO
      --hostname="inference@%h"
      --queues="${celeryInferenceQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.inference.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.inference.maxTasksPerChild}"
    )

    exec devenv shell -- celery "''${celery_worker_args[@]}"
  '';
  runLocalCeleryInferenceWorkerWheelScript = pkgs.writeShellScriptBin "${celeryInferenceWorkerScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
      echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export VIDEO_TEMPORAL_INFERENCE_JOB_MODE="celery"
    export VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE="stream"
    ${optionalString (cfg.runtime.inferenceWorker.cudaVisibleDevices != null) ''
      export CUDA_VISIBLE_DEVICES="${cfg.runtime.inferenceWorker.cudaVisibleDevices}"
    ''}
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
    celery_worker_args=(
      --hostname="inference@%h"
      --queues="${celeryInferenceQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.inference.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.inference.maxTasksPerChild}"
    )
    printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
    exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
  '';
  runLocalCeleryTrainingWorkerScript = pkgs.writeShellScriptBin "${celeryTrainingWorkerScriptName}" ''
    set -euo pipefail

    cd "${repoDir}"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export MODEL_TRAINING_JOB_MODE="celery"
    export MODEL_TRAINING_STAGING_ROOT="${cfg.runtime.modelTrainingStagingRoot}"
    export CUDA_VISIBLE_DEVICES="${cfg.runtime.trainingWorker.cudaVisibleDevices}"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    ${devenvSyncCompatExports}

    celery_worker_args=(
      -A lx_annotate.celery:app
      worker
      --loglevel=INFO
      --hostname="model-training@%h"
      --queues="${celeryTrainingQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.training.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.training.maxTasksPerChild}"
    )

    exec devenv shell -- celery "''${celery_worker_args[@]}"
  '';
  runLocalCeleryTrainingWorkerWheelScript = pkgs.writeShellScriptBin "${celeryTrainingWorkerScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
      echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export MODEL_TRAINING_JOB_MODE="celery"
    export MODEL_TRAINING_STAGING_ROOT="${cfg.runtime.modelTrainingStagingRoot}"
    export CUDA_VISIBLE_DEVICES="${cfg.runtime.trainingWorker.cudaVisibleDevices}"
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
    celery_worker_args=(
      --hostname="model-training@%h"
      --queues="${celeryTrainingQueueName}"
      --concurrency="${toString cfg.runtime.workerPools.training.concurrency}"
      --prefetch-multiplier=1
      --max-tasks-per-child="${toString cfg.runtime.workerPools.training.maxTasksPerChild}"
    )
    printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
    exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
  '';
  runLocalAcceptanceWheelScript = pkgs.writeShellScriptBin "${acceptanceScriptName}" ''
    set -euo pipefail

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export MEDIA_URL="${envNginxProtectedMediaUrl}"

    source "${lxAnnotateRuntimeLib}"
    ensure_wheel_runtime_installed
    mkdir -p "${runtimeStorageRootPath}" "${runtimeStreamableVideoRootPath}" "${runtimeStreamableVideoRawRootPath}" "${runtimeStreamableVideoProcessedRootPath}"

    run_installed_django_command "${runtimeWheelVenvPath}/bin/python" check --fail-level CRITICAL
    run_installed_django_command "${runtimeWheelVenvPath}/bin/python" verify_encrypted_storage
    ${pkgs.curl}/bin/curl --fail --silent --show-error --insecure \
      --resolve "${cfg.django.hostname}:443:127.0.0.1" \
      "https://${cfg.django.hostname}/static/.vite/manifest.json" >/dev/null

    log "lx-annotate acceptance checks passed."
  '';
  runLocalMasterKeyCheckWheelScript = pkgs.writeShellScriptBin "${masterKeyCheckScriptName}" ''
    set -euo pipefail

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"
    export MEDIA_URL="${envNginxProtectedMediaUrl}"

    if [ -z "''${LX_ANNOTATE_MASTER_KEY_FILE:-}" ] || [ ! -r "$LX_ANNOTATE_MASTER_KEY_FILE" ] || [ ! -s "$LX_ANNOTATE_MASTER_KEY_FILE" ]; then
      echo "ERROR: LX_ANNOTATE_MASTER_KEY_FILE is not configured, readable, and non-empty; refusing to boot without validating encrypted storage."
      exit 1
    fi

    source "${lxAnnotateRuntimeLib}"
    ensure_wheel_runtime_installed
    mkdir -p "${runtimeStorageRootPath}" "${runtimeStreamableVideoRootPath}" "${runtimeStreamableVideoRawRootPath}" "${runtimeStreamableVideoProcessedRootPath}"

    run_installed_django_command "${runtimeWheelVenvPath}/bin/python" verify_encrypted_storage

    log "lx-annotate application master key check passed."
  '';
  sapImportScriptName = "runLocalSapImport";
  sapImportScriptBody = ''
    set -euo pipefail

    sap_drop_dir="${runtimeSapImportDirPath}"
    sap_processed_dir="${runtimeSapImportProcessedDirPath}"
    sap_failed_dir="${runtimeSapImportFailedDirPath}"
    mkdir -p "$sap_drop_dir" "$sap_processed_dir" "$sap_failed_dir" "${runtimeWatcherPreanonymizedDirPath}"

    wait_for_stable_zip() {
      local file_path="$1"
      local previous_size="-1"
      local stable_checks=0
      local current_size=""

      for _ in $(seq 1 20); do
        if [ ! -f "$file_path" ]; then
          return 1
        fi

        current_size="$(${pkgs.coreutils}/bin/stat -c %s "$file_path" 2>/dev/null || echo -1)"
        if [ "$current_size" = "$previous_size" ]; then
          stable_checks=$((stable_checks + 1))
          if [ "$stable_checks" -ge 2 ]; then
            return 0
          fi
        else
          stable_checks=0
          previous_size="$current_size"
        fi
        sleep 2
      done

      return 1
    }

    shopt -s nullglob
    for zip_path in "$sap_drop_dir"/*.zip; do
      zip_name="$(${pkgs.coreutils}/bin/basename "$zip_path")"
      if ! wait_for_stable_zip "$zip_path"; then
        echo "SAP import zip did not become stable in time: $zip_path"
        continue
      fi

      if [ ! -f "$zip_path" ]; then
        continue
      fi

      if sap_import_one "$zip_path"; then
        ${pkgs.coreutils}/bin/mv "$zip_path" "$sap_processed_dir/$zip_name"
      else
        echo "SAP import failed for $zip_path"
        ${pkgs.coreutils}/bin/mv "$zip_path" "$sap_failed_dir/$zip_name"
      fi
    done
  '';
  runLocalSapImportScript = pkgs.writeShellScriptBin "${sapImportScriptName}" ''
        source "${lxAnnotateEnvHelpers}"
        lx_annotate_export_base_env
        lx_annotate_export_storage_env "${envDataDir}"
        lx_annotate_export_encryption_env
        lx_annotate_export_db_env
        lx_annotate_export_secret_key_env
        export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
        ${devenvSyncCompatExports}

        sap_import_one() {
          cd "${repoDir}"
          VENV_PYTHON="${repoDir}/.devenv/state/venv/bin/python"
          if [ ! -x "$VENV_PYTHON" ]; then
            echo "ERROR: repo venv missing at $VENV_PYTHON"
            return 1
          fi

          secretspec run --provider env "$VENV_PYTHON" manage.py import_sap_ish_zip "$1" --output_dir "${runtimeWatcherPreanonymizedDirPath}"
        }

    ${sapImportScriptBody}
  '';
  runLocalSapImportWheelScript = pkgs.writeShellScriptBin "${sapImportScriptName}" ''
        set -euo pipefail

        if [ -z ${lib.escapeShellArg wheelSapImportCommand} ]; then
          echo "ERROR: runtime.commands.sapImport must be set when wheel mode enables SAP import."
          exit 1
        fi

        source "${lxAnnotateRuntimeLib}"
        source "${lxAnnotateEnvHelpers}"
        lx_annotate_export_wheel_service_env "${envDataDir}"
        ensure_wheel_runtime_installed

        sap_import_one() {
          sap_import_command=${lib.escapeShellArg wheelSapImportCommand}
          printf -v sap_zip_arg '%q' "$1"
          printf -v sap_output_arg '%q' "${runtimeWatcherPreanonymizedDirPath}"
          "${pkgs.bash}/bin/bash" -lc "$sap_import_command $sap_zip_arg --output_dir $sap_output_arg"
        }

    ${sapImportScriptBody}
  '';
  runLocalExportFramesScript = pkgs.writeShellScriptBin "${exportFramesScriptName}" ''
    set -euo pipefail

    # 1. Go to the repo (Cloned by the main boot service)
    cd "${repoDir}"

    # 2. Re-Export ALL necessary Environment Variables
    source "${lxAnnotateEnvHelpers}"
    exportFramesStorageRoot="${exportFramesStorageRootDefault}"
    if [ ! -d "$exportFramesStorageRoot" ] || [ ! -w "$exportFramesStorageRoot" ]; then
      exportFramesStorageRoot="${envDataDir}"
    fi

    lx_annotate_export_base_env
    lx_annotate_export_storage_env "$exportFramesStorageRoot"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    ${devenvSyncCompatExports}

    # 4. Ensure target directory exists
    exportFramesDir="$exportFramesStorageRoot/export/frames"
    mkdir -p "$exportFramesDir"

    # 5. Run export inside devenv shell
    if [ -f Makefile ] && command -v devenv >/dev/null 2>&1; then
      export STORAGE_DIR="$exportFramesStorageRoot/storage"
      export DATA_DIR="$exportFramesStorageRoot"
      exec "${makeBin}" REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" start-export
    fi

    exec devenv shell -- bash -c "STORAGE_DIR='$exportFramesStorageRoot/storage' DATA_DIR='$exportFramesStorageRoot' export-frames"
  '';
  runLocalExportFramesWheelScript = pkgs.writeShellScriptBin "${exportFramesScriptName}" ''
    set -euo pipefail

    if [ -z ${lib.escapeShellArg wheelExportFramesCommand} ]; then
      echo "ERROR: runtime.commands.exportFrames must be set when wheel mode enables the export service."
      exit 1
    fi

    source "${lxAnnotateEnvHelpers}"
    exportFramesStorageRoot="${exportFramesStorageRootDefault}"
    if [ ! -d "$exportFramesStorageRoot" ] || [ ! -w "$exportFramesStorageRoot" ]; then
      exportFramesStorageRoot="${envDataDir}"
    fi

    lx_annotate_export_wheel_service_env "$exportFramesStorageRoot"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"
    export STORAGE_DIR="$exportFramesStorageRoot/storage"
    export DATA_DIR="$exportFramesStorageRoot"

    mkdir -p "$exportFramesStorageRoot/export/frames"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    exec "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg wheelExportFramesCommand}
  '';

  runLocalDataRecoveryScript = pkgs.writeShellScriptBin "runLxAnnotateDataRecovery" ''
        set -euo pipefail
        target_dir="${envDataDir}"
        resolved_target_dir="$(${pkgs.coreutils}/bin/realpath -m "$target_dir")"
        marker_dir="$target_dir/logs"
        marker_file="$marker_dir/data_recovery_complete"
        repair_marker_file="$marker_dir/data_migration_repair_latest.log"
        state_file="${cfg.dataRecovery.stateFile}"
        state_dir="$(${pkgs.coreutils}/bin/dirname "$state_file")"
        previous_effective_dir=""
        use_wheel_runtime="${if useWheelRuntime then "true" else "false"}"
        mkdir -p "$target_dir" "$marker_dir" "$state_dir"

        if [ -f "$state_file" ]; then
          previous_effective_dir="$(${pkgs.gnugrep}/bin/grep '^LAST_EFFECTIVE_DATA_DIR=' "$state_file" | ${pkgs.coreutils}/bin/tail -n 1 | ${pkgs.coreutils}/bin/cut -d= -f2- || true)"
        fi

        if [ -n "$previous_effective_dir" ]; then
          resolved_previous_effective_dir="$(${pkgs.coreutils}/bin/realpath -m "$previous_effective_dir")"
        else
          resolved_previous_effective_dir=""
        fi

        recovery_already_current=false
        # Heavy data recovery is a one-time operation for a data root.  A successful
        # repair marker is required before skipping, so interrupted/corrupt repair
        # runs still fail closed and retry before the app starts.
        if [ "$resolved_previous_effective_dir" = "$resolved_target_dir" ] \
          && [ -f "$marker_file" ] \
          && ${pkgs.gnugrep}/bin/grep -q '^completed_at=' "$marker_file" \
          && [ -f "$repair_marker_file" ] \
          && ${pkgs.gnugrep}/bin/grep -q '^completed_at=' "$repair_marker_file"; then
          recovery_already_current=true
        fi

        if [ "$recovery_already_current" = "true" ] && [ "''${LX_ANNOTATE_FORCE_DATA_RECOVERY:-false}" != "true" ]; then
          echo "Data recovery already completed for $resolved_target_dir; skipping heavy recovery and managed payload repair."
          exit 0
        fi

        source "${lxAnnotateRuntimeLib}"
        source "${lxAnnotateEnvHelpers}"
        lx_annotate_export_base_env
        lx_annotate_export_storage_env "${envDataDir}"
        lx_annotate_export_encryption_env
        lx_annotate_export_django_paths_env
        lx_annotate_export_db_env
        lx_annotate_export_secret_key_env
        lx_annotate_export_oidc_env

        export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
        export WORKING_DIR="${runtimeWorkingDir}"
        export HOME_DIR="${endoreg-service-user-home}"
        export XDG_DATA_HOME="${runtimeRootPath}"
        export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${envDataDir}"
        export LX_ANNOTATE_DATA_DIR="${envDataDir}"
        export LX_ANNOTATE_DEFAULT_CENTER="${envDefaultCenter}"
        export TESSDATA_PREFIX="${cfg.runtime.tessdataPrefix}"
        export PYTORCH_ALLOC_CONF="${cfg.runtime.pytorchAllocConf}"

        if [ "$use_wheel_runtime" = "true" ]; then
          ensure_wheel_runtime_installed
          if [ -x "${runtimeWheelVenvPath}/bin/python" ]; then
            echo "Applying Django migrations before data recovery helper commands."
            run_installed_django_command "${runtimeWheelVenvPath}/bin/python" migrate --noinput
          fi
        fi

        sync_source_dir() {
          local source_root="$1"
          local label="$2"
          local resolved_source_root

          resolved_source_root="$(${pkgs.coreutils}/bin/realpath -m "$source_root")"

          if [ "$resolved_source_root" = "$resolved_target_dir" ]; then
            echo "Skipping $label source; source and target are identical: $resolved_source_root"
            return 0
          fi

          if [ ! -d "$source_root" ]; then
            echo "Skipping $label source; directory not present: $source_root"
            return 0
          fi

          if [ -z "$(${pkgs.findutils}/bin/find "$source_root" -mindepth 1 -type f -print -quit 2>/dev/null || true)" ]; then
            echo "Skipping $label source; no files present: $source_root"
            return 0
          fi

          echo "Recovering $label payload from $source_root into $target_dir"
          ${pkgs.rsync}/bin/rsync \
            -a \
            --delay-updates \
            --partial \
            --partial-dir=.lx-annotate-rsync-partial \
            --ignore-existing \
            --omit-dir-times \
            --chmod=F640,D750 \
            "$source_root/" "$target_dir/"
        }



        run_installed_django_command() {
          local helper_python="$1"
          shift
          "$helper_python" -m django "$@" --settings=lx_annotate.settings.settings_prod
        }

        write_repair_failure() {
          local repair_output="$1"
          {
            printf 'failed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
            printf 'target_dir=%s\n' "$target_dir"
            printf '%s\n' "$repair_output"
          } > "$repair_marker_file"
          chmod 0640 "$repair_marker_file"
          printf '%s\n' "$repair_output" >&2
          echo "Managed payload repair failed; see $repair_marker_file for details." | ${pkgs.coreutils}/bin/tee -a "$repair_marker_file" >&2
        }

        repair_managed_runtime_payloads() {
          local helper_python="$1"
          local repair_output=""
          local has_master_key="false"

          if [ -z "$helper_python" ] || [ ! -x "$helper_python" ]; then
            echo "Skipping managed payload repair; helper python unavailable." | ${pkgs.coreutils}/bin/tee "$repair_marker_file"
            return 0
          fi

          if [ -n "''${LX_ANNOTATE_MASTER_KEY:-}" ] || [ -n "''${LX_ANNOTATE_MASTER_KEY_FILE:-}" ]; then
            has_master_key="true"
          fi

          if [ "$has_master_key" != "true" ]; then
            echo "Skipping managed payload repair; LX_ANNOTATE_MASTER_KEY or LX_ANNOTATE_MASTER_KEY_FILE is not configured for this runtime." | ${pkgs.coreutils}/bin/tee "$repair_marker_file"
            return 0
          fi

          echo "Repair preflight: HAS_MASTER_KEY=$has_master_key"
          echo "Repairing managed runtime payloads that may have been copied in plaintext by the legacy migration helper."
          if [ "$use_wheel_runtime" = "true" ]; then
            repair_output="$(run_installed_django_command "$helper_python" repair_managed_payloads 2>&1)" || {
              write_repair_failure "$repair_output"
              return 1
            }
          else
            repair_output="$({
              cd "${repoDir}"
              "$helper_python" "${repoDir}/manage.py" repair_managed_payloads
            } 2>&1)" || {
              write_repair_failure "$repair_output"
              return 1
            }
          fi

          {
            printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
            printf 'target_dir=%s\n' "$target_dir"
            printf '%s\n' "$repair_output"
          } > "$repair_marker_file"
          chmod 0640 "$repair_marker_file"
          echo "Managed payload repair marker written to $repair_marker_file"
          return 0
        }

        if [ -n "$previous_effective_dir" ]; then
          if [ "$resolved_previous_effective_dir" != "$resolved_target_dir" ]; then
            sync_source_dir "$previous_effective_dir" "previous effective data dir"
          else
            echo "Configured data dir unchanged since last successful recovery: $resolved_target_dir"
          fi
        else
          echo "No previous effective data dir recorded in $state_file"
        fi

        migration_helper_python=""
        if [ "$use_wheel_runtime" = "true" ]; then
          if [ -x "${runtimeWheelVenvPath}/bin/python" ]; then
            migration_helper_python="${runtimeWheelVenvPath}/bin/python"
          fi
        elif [ -f "${repoDir}/scripts/migrate_data_dir.py" ] && [ -x "${repoDir}/.devenv/state/venv/bin/python" ]; then
          migration_helper_python="${repoDir}/.devenv/state/venv/bin/python"
        fi

        if [ -n "$migration_helper_python" ]; then
          if [ "$use_wheel_runtime" = "true" ]; then
            echo "Running installed migrate_data_dir command into $target_dir"
            if ! run_installed_django_command "$migration_helper_python" migrate_data_dir "${cfg.dataRecovery.legacyDataDir}"; then
              echo "Migration helper failed; falling back to compatibility rsync."
              sync_source_dir "${cfg.dataRecovery.legacyDataDir}" "legacy repo data"
              sync_source_dir "${cfg.dataRecovery.legacyMediaDir}" "legacy media"
            else
              # Keep compatibility overlays for payload classes the Django helper may
              # not move in wheel deployments.
              sync_source_dir "${cfg.dataRecovery.legacyDataDir}" "legacy data compatibility overlay"
              sync_source_dir "${cfg.dataRecovery.legacyMediaDir}" "legacy media compatibility overlay"
            fi
          else
            echo "Running lx-annotate repo migration helper into $target_dir"
            cd "${repoDir}"
            if ! "$migration_helper_python" "${repoDir}/scripts/migrate_data_dir.py" \
              --repo-root "${repoDir}" \
              --target "$target_dir"; then
              echo "Migration helper failed; falling back to compatibility rsync."
              sync_source_dir "${cfg.dataRecovery.legacyDataDir}" "legacy repo data"
              sync_source_dir "${cfg.dataRecovery.legacyMediaDir}" "legacy media"
            fi
          fi
        else
          echo "Migration helper unavailable; falling back to compatibility rsync."
          sync_source_dir "${cfg.dataRecovery.legacyDataDir}" "legacy repo data"
          sync_source_dir "${cfg.dataRecovery.legacyMediaDir}" "legacy media"
        fi

        repair_managed_runtime_payloads "$migration_helper_python"

        if [ -n "$migration_helper_python" ]; then
          echo "Marking migration-created upload job source files as cleanup-eligible after data recovery."
          if [ "$use_wheel_runtime" = "true" ]; then
            run_installed_django_command "$migration_helper_python" migration_mark_eligible --apply
          else
            cd "${repoDir}"
            "$migration_helper_python" "${repoDir}/manage.py" migration_mark_eligible --apply
          fi

          echo "Backfilling cleanup eligibility for failed/quarantined delete-after-success upload jobs."
          if [ "$use_wheel_runtime" = "true" ]; then
            run_installed_django_command "$migration_helper_python" shell -c '
    from django.utils import timezone
    from endoreg_db.models.hub.upload_job import UploadJob

    updated = 0
    now = timezone.now()
    qs = UploadJob.objects.filter(
        retention_policy=UploadJob.RetentionPolicy.DELETE_AFTER_SUCCESS,
        source_file_persisted=True,
        cleanup_status=UploadJob.CleanupStatus.PENDING,
        status__in=[UploadJob.Status.ERROR, UploadJob.Status.LOST],
    ).order_by("created_at")

    for upload_job in qs.iterator():
        provenance = getattr(upload_job, "processing_provenance", None) or {}
        quarantined_path = str(provenance.get("quarantined_path", "") or "").strip()
        quarantined_sidecar_path = str(provenance.get("quarantined_sidecar_path", "") or "").strip()
        if not quarantined_path and not quarantined_sidecar_path:
            continue
        update_fields = ["cleanup_status", "updated_at"]
        if upload_job.source_file_delete_eligible_at is None:
            upload_job.source_file_delete_eligible_at = now
            update_fields.append("source_file_delete_eligible_at")
        upload_job.cleanup_status = UploadJob.CleanupStatus.ELIGIBLE
        upload_job.save(update_fields=update_fields)
        updated += 1

    print(f"updated_failed_upload_jobs={updated}")
    '
          else
            cd "${repoDir}"
            "$migration_helper_python" "${repoDir}/manage.py" shell -c '
    from django.utils import timezone
    from endoreg_db.models.hub.upload_job import UploadJob

    updated = 0
    now = timezone.now()
    qs = UploadJob.objects.filter(
        retention_policy=UploadJob.RetentionPolicy.DELETE_AFTER_SUCCESS,
        source_file_persisted=True,
        cleanup_status=UploadJob.CleanupStatus.PENDING,
        status__in=[UploadJob.Status.ERROR, UploadJob.Status.LOST],
    ).order_by("created_at")

    for upload_job in qs.iterator():
        provenance = getattr(upload_job, "processing_provenance", None) or {}
        quarantined_path = str(provenance.get("quarantined_path", "") or "").strip()
        quarantined_sidecar_path = str(provenance.get("quarantined_sidecar_path", "") or "").strip()
        if not quarantined_path and not quarantined_sidecar_path:
            continue
        update_fields = ["cleanup_status", "updated_at"]
        if upload_job.source_file_delete_eligible_at is None:
            upload_job.source_file_delete_eligible_at = now
            update_fields.append("source_file_delete_eligible_at")
        upload_job.cleanup_status = UploadJob.CleanupStatus.ELIGIBLE
        upload_job.save(update_fields=update_fields)
        updated += 1

    print(f"updated_failed_upload_jobs={updated}")
    '
          fi

          echo "Reaping upload job source files after data recovery."
          if [ "$use_wheel_runtime" = "true" ]; then
            run_installed_django_command "$migration_helper_python" reap_upload_job_sources
          else
            cd "${repoDir}"
            "$migration_helper_python" "${repoDir}/manage.py" reap_upload_job_sources
          fi
        else
          echo "Skipping upload job source reaping; Django helper python unavailable."
        fi

        {
          printf 'LAST_EFFECTIVE_DATA_DIR=%s\n' "$resolved_target_dir"
          printf 'UPDATED_AT=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
        } > "$state_file.tmp"
        ${pkgs.coreutils}/bin/mv "$state_file.tmp" "$state_file"
        chmod 0640 "$state_file"

        printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)" > "$marker_file"
        chmod 0640 "$marker_file"
        echo "Data recovery marker written to $marker_file"
  '';

  runLocalDataCleanupScript = pkgs.writeShellScriptBin "runLxAnnotateDataCleanup" ''
        set -euo pipefail

        runtime_root="${envDataDir}"
        archive_root="${cfg.dataCleanup.archiveDir}"
        marker_dir="$runtime_root/logs"
        marker_file="$marker_dir/data_cleanup_latest.log"

        mkdir -p "$marker_dir"

        if [ ! -d "$runtime_root" ]; then
          echo "Skipping cleanup; runtime root missing: $runtime_root"
          exit 0
        fi

        if [ ! -d "${config.roles.endoreg-client.paths.storagePersistingMountPoint}" ]; then
          echo "Skipping cleanup; persisting storage mount missing: ${config.roles.endoreg-client.paths.storagePersistingMountPoint}"
          exit 0
        fi

        mkdir -p "$archive_root"

        moved_count=0
        skipped_count=0

        move_duplicate_tree() {
          local source_root="$1"
          local runtime_target_root="$2"
          local label="$3"

          if [ ! -d "$source_root" ]; then
            echo "Skipping $label source; directory not present: $source_root"
            return 0
          fi

          while IFS= read -r -d "" source_file; do
            local rel_path runtime_file archive_file archive_dir

            rel_path="''${source_file#"$source_root"/}"
            runtime_file="$runtime_target_root/$rel_path"
            if [ ! -f "$runtime_file" ]; then
              skipped_count=$((skipped_count + 1))
              continue
            fi

            if ! ${pkgs.diffutils}/bin/cmp -s "$source_file" "$runtime_file"; then
              skipped_count=$((skipped_count + 1))
              continue
            fi

            archive_file="$archive_root/$label/$rel_path"
            archive_dir="$(${pkgs.coreutils}/bin/dirname "$archive_file")"
            ${pkgs.coreutils}/bin/mkdir -p "$archive_dir"

            if [ -e "$archive_file" ]; then
              if ${pkgs.diffutils}/bin/cmp -s "$source_file" "$archive_file"; then
                ${pkgs.coreutils}/bin/rm -f "$source_file"
              else
                archive_file="$archive_file.$(${pkgs.coreutils}/bin/date +%s)"
                ${pkgs.coreutils}/bin/mv "$source_file" "$archive_file"
              fi
            else
              ${pkgs.coreutils}/bin/mv "$source_file" "$archive_file"
            fi

            moved_count=$((moved_count + 1))
          done < <(${pkgs.findutils}/bin/find "$source_root" -type f -print0)

          ${pkgs.findutils}/bin/find "$source_root" -depth -type d -empty -delete || true
        }

        move_duplicate_tree "${cfg.dataCleanup.legacyProcessedReportDir}" "${cfg.dataCleanup.runtimeProcessedReportDir}" "legacy-data/${processedReportDirName}"
        move_duplicate_tree "${cfg.dataCleanup.legacyProcessedVideoDir}" "${cfg.dataCleanup.runtimeProcessedVideoDir}" "legacy-data/${processedVideoDirName}"
        move_duplicate_tree "${cfg.dataCleanup.legacyMediaProcessedReportDir}" "${cfg.dataCleanup.runtimeProcessedReportDir}" "legacy-media/${processedReportDirName}"
        move_duplicate_tree "${cfg.dataCleanup.legacyMediaProcessedVideoDir}" "${cfg.dataCleanup.runtimeProcessedVideoDir}" "legacy-media/${processedVideoDirName}"

        {
          printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
          printf 'runtime_root=%s\n' "$runtime_root"
          printf 'archive_root=%s\n' "$archive_root"
          printf 'moved_count=%s\n' "$moved_count"
          printf 'skipped_count=%s\n' "$skipped_count"
        } > "$marker_file"

        chmod 0640 "$marker_file"

        echo "Cleanup completed. moved=$moved_count skipped=$skipped_count archive=$archive_root"
      '';

  runLocalEmergencyStorageReliefScript = pkgs.writeShellScriptBin "${emergencyStorageReliefScriptName}" ''
        set -euo pipefail

        json_log() {
          "${pkgs.python3}/bin/python3" - "$1" "$2" <<-'PY'
    import json
    import sys
    print(json.dumps({
        "event": "lx_annotate_storage_relief_preflight",
        "status": sys.argv[1],
        "detail": sys.argv[2],
    }, sort_keys=True))
    PY
        }

        external_mount_point=${lib.escapeShellArg cfg.storageRelief.externalMountPoint}
        expected_device_id=${lib.escapeShellArg (if cfg.storageRelief.expectedDeviceId == null then "" else cfg.storageRelief.expectedDeviceId)}
        expected_device_part=${lib.escapeShellArg cfg.storageRelief.expectedDevicePart}
        expected_fs_uuid=${lib.escapeShellArg (if cfg.storageRelief.expectedFsUuid == null then "" else cfg.storageRelief.expectedFsUuid)}

        if [ "${if cfg.storageRelief.requireExternalMount then "true" else "false"}" = "true" ]; then
          if [ -z "$expected_device_id" ] && [ -z "$expected_fs_uuid" ]; then
            json_log error "storageRelief requires expectedDeviceId or expectedFsUuid"
            exit 1
          fi

          if ! "${pkgs.util-linux}/bin/mountpoint" -q "$external_mount_point"; then
            json_log error "external relief mount is not mounted: $external_mount_point"
            exit 1
          fi

          actual_source="$("${pkgs.util-linux}/bin/findmnt" -n -o SOURCE --target "$external_mount_point" || true)"
          if [ -z "$actual_source" ]; then
            json_log error "unable to resolve mounted source for $external_mount_point"
            exit 1
          fi
          actual_source_resolved="$("${pkgs.coreutils}/bin/readlink" -f "$actual_source" 2>/dev/null || printf '%s' "$actual_source")"

          if [ -n "$expected_device_id" ]; then
            expected_path="/dev/disk/by-id/$expected_device_id-$expected_device_part"
            if [ ! -e "$expected_path" ]; then
              json_log error "configured relief device path does not exist: $expected_path"
              exit 1
            fi
            expected_resolved="$("${pkgs.coreutils}/bin/readlink" -f "$expected_path")"
            if [ "$actual_source_resolved" != "$expected_resolved" ]; then
              json_log error "mounted source $actual_source_resolved does not match expected $expected_resolved"
              exit 1
            fi
          fi

          if [ -n "$expected_fs_uuid" ]; then
            actual_fs_uuid="$("${pkgs.util-linux}/bin/findmnt" -n -o UUID --target "$external_mount_point" 2>/dev/null || true)"
            if [ -z "$actual_fs_uuid" ]; then
              actual_fs_uuid="$("${pkgs.util-linux}/bin/blkid" -s UUID -o value "$actual_source_resolved" 2>/dev/null || true)"
            fi
            if [ "$actual_fs_uuid" != "$expected_fs_uuid" ]; then
              json_log error "mounted filesystem UUID $actual_fs_uuid does not match expected $expected_fs_uuid"
              exit 1
            fi
          fi
        fi

        source "${lxAnnotateRuntimeLib}"

        if [ "${if useWheelRuntime then "true" else "false"}" = "true" ]; then
          source "${lxAnnotateEnvHelpers}"
          lx_annotate_export_wheel_service_env "${envDataDir}"
          ensure_wheel_runtime_installed
          helper_python="${runtimeWheelVenvPath}/bin/python"
        else
          lx_annotate_export_runtime_env
          lx_annotate_activate_runtime
          helper_python="$(command -v python)"
        fi

        if [ ! -x "$helper_python" ]; then
          json_log error "Python runtime missing: $helper_python"
          exit 1
        fi

        exec "$helper_python" "${emergencyStorageReliefHelper}" --config "${emergencyStorageReliefConfig}"
      '';

  runLocalHubBackupScript = pkgs.writeShellScriptBin "runLxAnnotateHubBackup" ''
        set -euo pipefail

        runtime_root="${cfg.hub.backup.sourceRuntimeDir}"
        incoming_root="${cfg.hub.backup.incomingDir}"
        snapshot_root="${cfg.hub.backup.snapshotDir}"
        manifest_root="${cfg.hub.backup.manifestDir}"
        latest_link="$snapshot_root/latest"
        retain_count="${toString cfg.hub.backup.retainCount}"
        host_name="${config.networking.hostName}"
        timestamp="$(${pkgs.coreutils}/bin/date -u +%Y%m%dT%H%M%SZ)"
        pending_snapshot="$snapshot_root/.pending-$timestamp"
        completed_snapshot="$snapshot_root/$timestamp"
        manifest_file="$manifest_root/$timestamp.json"
        previous_snapshot=""

        if [ ! -d "$runtime_root" ]; then
          echo "Skipping hub backup; runtime root missing: $runtime_root"
          exit 0
        fi

        install -d -m 0750 "$incoming_root" "$snapshot_root" "$manifest_root"
        rm -rf "$pending_snapshot"
        install -d -m 0750 "$pending_snapshot"

        if [ -L "$latest_link" ]; then
          previous_snapshot="$(${pkgs.coreutils}/bin/readlink -f "$latest_link" 2>/dev/null || true)"
        fi

        rsync_cmd=(
          ${pkgs.rsync}/bin/rsync
          -a
          --delete
          --numeric-ids
          --chmod=F640,D750
        )

        if [ -n "$previous_snapshot" ] && [ -d "$previous_snapshot" ]; then
          rsync_cmd+=(--link-dest "$previous_snapshot")
        fi

        ${lib.concatStringsSep "\n" (map (pattern: "rsync_cmd+=(--exclude ${lib.escapeShellArg pattern})") cfg.hub.backup.exclude)}

        rsync_cmd+=("$runtime_root/" "$pending_snapshot/")
        "''${rsync_cmd[@]}"

        ${pkgs.coreutils}/bin/mv "$pending_snapshot" "$completed_snapshot"
        ln -sfn "$completed_snapshot" "$latest_link"

        file_count="$(${pkgs.findutils}/bin/find "$completed_snapshot" -type f | ${pkgs.coreutils}/bin/wc -l | ${pkgs.gawk}/bin/awk '{print $1}')"
        size_bytes="$(${pkgs.findutils}/bin/find "$completed_snapshot" -type f -printf '%s\n' | ${pkgs.gawk}/bin/awk '{sum += $1} END {print sum + 0}')"

        ${pkgs.jq}/bin/jq -n \
          --arg generated_at "$(${pkgs.coreutils}/bin/date -u --iso-8601=seconds)" \
          --arg hostname "$host_name" \
          --arg runtime_root "$runtime_root" \
          --arg incoming_root "$incoming_root" \
          --arg snapshot_dir "$completed_snapshot" \
          --arg latest_snapshot "$(${pkgs.coreutils}/bin/readlink -f "$latest_link")" \
          --argjson retain_count "$retain_count" \
          --argjson file_count "$file_count" \
          --argjson size_bytes "$size_bytes" \
          --argjson exclude '${builtins.toJSON cfg.hub.backup.exclude}' \
          '{
            generated_at: $generated_at,
            hostname: $hostname,
            runtime_root: $runtime_root,
            incoming_root: $incoming_root,
            snapshot_dir: $snapshot_dir,
            latest_snapshot: $latest_snapshot,
            retain_count: $retain_count,
            file_count: $file_count,
            size_bytes: $size_bytes,
            exclude: $exclude
          }' > "$manifest_file"

        if [ "$retain_count" -gt 0 ]; then
          mapfile -t snapshots_to_prune < <(
            ${pkgs.findutils}/bin/find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
              | ${pkgs.coreutils}/bin/sort -r \
              | ${pkgs.coreutils}/bin/tail -n +$((retain_count + 1))
          )

          for snapshot_name in "''${snapshots_to_prune[@]}"; do
            [ -n "$snapshot_name" ] || continue
            ${pkgs.coreutils}/bin/rm -rf "$snapshot_root/$snapshot_name"
          done
        fi

        echo "Hub backup completed. snapshot=$completed_snapshot manifest=$manifest_file files=$file_count size_bytes=$size_bytes"
  '';

  lxAnnotateEncryptedDataMountScript = pkgs.writeShellScriptBin "lx-annotate-encrypted-data-mount" ''
    set -euo pipefail

    mount_point="${envDataDir}"
    mapper_name="${cfg.runtime.managedEncryptedData.mapperName}"
    mapper_path="/dev/mapper/$mapper_name"
    luks_uuid="${if cfg.runtime.managedEncryptedData.luksUuid == null then "" else cfg.runtime.managedEncryptedData.luksUuid}"
    luks_uuid_file="${if cfg.runtime.managedEncryptedData.luksUuidFile == null then "" else toString cfg.runtime.managedEncryptedData.luksUuidFile}"
    key_file="${if cfg.runtime.managedEncryptedData.keyFile == null then "" else toString cfg.runtime.managedEncryptedData.keyFile}"

    if [ -z "$luks_uuid" ] && [ -n "$luks_uuid_file" ] && [ -f "$luks_uuid_file" ]; then
      luks_uuid="$(tr -d '\n' < "$luks_uuid_file")"
    fi

    if [ -z "$luks_uuid" ]; then
      echo "ERROR: runtime.managedEncryptedData.luksUuid is not set and no luksUuidFile was readable."
      exit 1
    fi

    if [ -z "$key_file" ] || [ ! -f "$key_file" ]; then
      echo "ERROR: encrypted data key file is missing: $key_file"
      exit 1
    fi

    install -d -m 0750 "$mount_point"

    if mountpoint -q "$mount_point"; then
      echo "Encrypted data already mounted at $mount_point"
      exit 0
    fi

    if ! cryptsetup status "$mapper_name" >/dev/null 2>&1; then
      cryptsetup open "UUID=$luks_uuid" "$mapper_name" --key-file "$key_file"
    fi

    if [ ! -b "$mapper_path" ]; then
      echo "ERROR: mapper device not available after unlock: $mapper_path"
      exit 1
    fi

    mount_cmd=(${pkgs.util-linux}/bin/mount)
    if [ -n "${cfg.runtime.managedEncryptedData.fsType}" ]; then
      mount_cmd+=(-t "${cfg.runtime.managedEncryptedData.fsType}")
    fi
    ${
      optionalString (encryptedDataMountOptions != "") ''
        mount_cmd+=(-o "${encryptedDataMountOptions}")
      ''
    }
    mount_cmd+=("$mapper_path" "$mount_point")
    "''${mount_cmd[@]}"

    chown "${cfg.runtime.managedEncryptedData.owner}:${cfg.runtime.managedEncryptedData.group}" "$mount_point"
    chmod "${cfg.runtime.managedEncryptedData.dirMode}" "$mount_point"
  '';

  lxAnnotateEncryptedDataUmountScript = pkgs.writeShellScriptBin "lx-annotate-encrypted-data-umount" ''
    set -euo pipefail

    mount_point="${envDataDir}"
    mapper_name="${cfg.runtime.managedEncryptedData.mapperName}"

    if mountpoint -q "$mount_point"; then
      ${pkgs.util-linux}/bin/umount "$mount_point"
    fi

    if cryptsetup status "$mapper_name" >/dev/null 2>&1; then
      cryptsetup close "$mapper_name"
    fi
  '';

in
{
  helpers = {
    inherit makeBin lxAnnotateEnvHelpers;
  };

  scriptNames = {
    inherit
      acceptanceScriptName
      masterKeyCheckScriptName
      celeryFrameExtractionWorkerScriptName
      celeryFfmpegWorkerScriptName
      celeryInferenceWorkerScriptName
      celeryPipelineWorkerScriptName
      celeryTrainingWorkerScriptName
      celeryWorkerScriptName
      emergencyStorageReliefScriptName
      loadBaseDataWheelScriptName
      migrateWheelScriptName
      watcherScriptName
      sapImportScriptName
      migrateVideoStreamableStorageScriptName;
  };

  packages = {
    inherit
      lxAnnotateSyncScript
      lxAnnotatePrepareScript
      lxAnnotateBuildScript
      lxAnnotateMigrateScript
      lxAnnotateMigrateVideoStreamableStorageScript
      lxAnnotateBootstrapScript
      runLocalLxAnnotateStartScript
      runLocalLxAnnotateScript
      runLocalMigrateWheelScript
      runLocalLoadBaseDataWheelScript
      runLocalLxAnnotateWheelScript
      runLocalAcceptanceScript
      runLocalAcceptanceWheelScript
      runLocalMasterKeyCheckWheelScript
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
      runLocalFileWatcherScript
      runLocalFileWatcherWheelScript
      runLocalSapImportScript
      runLocalSapImportWheelScript
      runLocalExportFramesScript
      runLocalExportFramesWheelScript
      runLocalDataRecoveryScript
      runLocalDataCleanupScript
      runLocalEmergencyStorageReliefScript
      runLocalHubBackupScript
      lxAnnotateEncryptedDataMountScript
      lxAnnotateEncryptedDataUmountScript;
  };
}
