args@{
  config,
  lib,
  pkgs,
  cfg,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (lib) optionalString;

  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-user-home
    endoreg-service-group-name
    ;
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
    viteSourcePath
    envDataDir
    envConfDir
    makeCacheDir
    envConfTemplateDir
    envSystemdFilePath
    envAssetDir
    dataRecoveryStateDir
    dataRecoveryStateFile
    ;
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
    envRunVideoTests
    envSkipExpensiveTests
    envViteEnableDebug
    ;
  inherit (runtime.runtime)
    useWheelRuntime
    pythonInterpreter
    wheelFilePath
    packageVersion
    ;
  inherit (runtime.defaults)
    exportFramesStorageRootDefault
    processedReportDirName
    processedVideoDirName
    ;
  makeBin = "${pkgs.gnumake}/bin/make";
  envScripts = import ./scripts/env.nix args;
  inherit (envScripts)
    celeryBrokerUrl
    celeryDefaultQueueName
    celeryPipelineQueueName
    celeryFrameExtractionQueueName
    celeryFfmpegMediaQueueName
    celeryInferenceQueueName
    celeryTrainingQueueName
    celeryMaintenanceQueueName
    ffmpegTranscodeTimeoutSeconds
    lxAnnotateEnvHelpers
    ;

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

  frontendAssetScripts = import ./scripts/frontend-assets.nix args;
  inherit (frontendAssetScripts)
    alignEnvFileScript
    viteManifestEntryScript
    ;

  syncScriptName = "lx-annotate-sync";
  prepareScriptName = "lx-annotate-prepare";
  buildScriptName = "lx-annotate-build";
  migrateScriptName = "lx-annotate-migrate";
  migrateVideoStreamableStorageScriptName = "lx-annotate-migrate-video-streamable-storage";
  loadBaseDataServiceName = "lx-annotate-load-base-data.service";
  masterKeyCheckServiceName = "lx-annotate-master-key-check.service";
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
  storageReliefScripts = import ./scripts/storage-relief.nix args;
  inherit (storageReliefScripts)
    emergencyStorageReliefConfig
    emergencyStorageReliefHelper
    ;

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
          local wheelhouse_path="${
            optionalString (cfg.runtime.wheelhousePath != null) (toString cfg.runtime.wheelhousePath)
          }"
          local wheelhouse_hash="no-wheelhouse"
          local pip_install_args=""
          local wheel_install_stamp_file="${runtimeRootPath}/.wheel-install.sha256"
          local wheel_install_lock_file="${runtimeRootPath}/.wheel-install.lock"
          local installed_hash=""
          local canonical_wheel_name=""
          local staged_wheel_path=""
          local install_hash=""
          local wheel_installer_revision="stop-workers-before-wheel-install-v2-incremental-pip-cache"
          local venv_created="false"
          local pip_cache_dir="${runtimeRootPath}/pip-cache"

          if [ -z "${wheelFilePath}" ]; then
            die "services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set in wheel mode."
          fi

          install -d -m 0750 "${runtimeRootPath}" "${runtimeWheelRootPath}" "${runtimeWheelVenvPath}" "$pip_cache_dir" "${envConfDir}" "${envDataDir}"
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
            export PIP_CACHE_DIR="$pip_cache_dir"
            export PIP_DISABLE_PIP_VERSION_CHECK=1
            # shellcheck disable=SC2086
            "${runtimeWheelVenvPath}/bin/pip" install --upgrade $pip_install_args "$staged_wheel_path"
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
          # Host-owned values only. lx-annotate derives DATA_DIR, STORAGE_DIR,
          # PROTECTED_MEDIA_ROOT, and streamable video roots from this contract.
          cat <<EOF
    HOME_DIR=${endoreg-service-user-home}
    LX_ANNOTATE_ENCRYPTED_DATA_DIR=${envDataDir}
    CONF_DIR=${envConfDir}
    CONF_TEMPLATE_DIR=${envConfTemplateDir}
    WORKING_DIR=${repoDir}
    DJANGO_STATIC_ROOT=${djangoStaticRootPath}
    ASSET_DIR=${envAssetDir}
    XDG_DATA_HOME=${runtimeRootPath}
    LX_ANNOTATE_PACKAGE_VERSION=${packageVersion}
    ${optionalString (
      cfg.runtime.masterKeyFile != null
    ) "LX_ANNOTATE_MASTER_KEY_FILE=${toString cfg.runtime.masterKeyFile}"}
    DJANGO_SECRET_KEY_FILE=${toString cfg.django.djangoSecretKeyFile}
    DJANGO_DB_ENGINE=django.db.backends.postgresql
    DJANGO_DB_NAME=${cfg.database.name}
    DJANGO_DB_USER=${cfg.database.user}
    DJANGO_DB_PASSWORD_FILE=${envConfDir}/db_pwd
    DJANGO_DB_HOST=${cfg.database.host}
    DJANGO_DB_PORT=${toString cfg.database.port}
    DJANGO_DB_SSLMODE=${cfg.database.sslMode}
    DJANGO_KEYCLOAK_CLIENT_SECRET_FILE=${toString cfg.django.keycloakSecretFile}
    OIDC_RP_CLIENT_ID=${cfg.django.keycloakClientId}
    ENDOREG_DEPLOYMENT_ROLE=${envDeploymentRole}
    ENDOREG_HUB_MODE=${if cfg.hub.enable then "true" else "false"}
    ENDOREG_ENABLE_HUB_TRANSFERS=${if cfg.hub.transferApi.enable then "true" else "false"}
    ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=${
      if cfg.hub.transferApi.requireSecureTransport then "true" else "false"
    }
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
    CELERY_FRAME_EXTRACTION_REQUIRE_SECURE_TRANSPORT=${
      if cfg.runtime.celeryBroker.requireSecureTransport then "true" else "false"
    }
    CELERY_FFMPEG_MEDIA_REQUIRE_SECURE_TRANSPORT=${
      if cfg.runtime.celeryBroker.requireSecureTransport then "true" else "false"
    }
    CELERY_BROKER_SECURE_TRANSPORT_CONFIRMED=${
      if cfg.runtime.celeryBroker.secureTransportConfirmed then "true" else "false"
    }
    MODEL_TRAINING_JOB_MODE=celery
    MODEL_TRAINING_STAGING_ROOT=${cfg.runtime.modelTrainingStagingRoot}
    VIDEO_POST_VALIDATION_JOB_MODE=celery
    VIDEO_TEMPORAL_INFERENCE_JOB_MODE=celery
    VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE=stream
    SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
    REQUESTS_CA_BUNDLE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
    VITE_ENABLE_DEBUG=${envViteEnableDebug}
    HTTP_PROTOCOL=${envHttpProtocol}
    DJANGO_HOST=${envDjangoHost}
    DJANGO_PORT=${envDjangoPort}
    BASE_URL=${envBaseUrl}
    DJANGO_ALLOWED_HOSTS=${envAllowedHosts}
    ALLOWED_HOSTS=${envAllowedHosts}
    DJANGO_CORS_ALLOWED_ORIGINS=${envCorsAllowedOrigins}
    DJANGO_CSRF_TRUSTED_ORIGINS=${envCorsAllowedOrigins}
    TIME_ZONE=${cfg.django.timeZone}
    RUN_VIDEO_TESTS=${envRunVideoTests}
    SKIP_EXPENSIVE_TESTS=${envSkipExpensiveTests}
    WATCHER_VIDEO_DIR=${runtimeWatcherVideoDirPath}
    WATCHER_REPORT_DIR=${runtimeWatcherReportDirPath}
    WATCHER_PREANONYMIZED_DIR=${runtimeWatcherPreanonymizedDirPath}
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
    TESSDATA_PREFIX=${cfg.runtime.tessdataPrefix}
    PYTORCH_ALLOC_CONF=${cfg.runtime.pytorchAllocConf}
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
          : "''${LX_ANNOTATE_ALLOW_DESTRUCTIVE_GIT_RESET:=${
            if cfg.source.updateOnBoot then "true" else "false"
          }}"
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

    if [ "${
      if useWheelRuntime then "true" else "false"
    }" = "true" ] && [ -z ${lib.escapeShellArg wheelMediaMigrationCommand} ]; then
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
  celeryWorkerResourceEnv = ''
    export OMP_NUM_THREADS="1"
    export OPENBLAS_NUM_THREADS="1"
    export MKL_NUM_THREADS="1"
    export NUMEXPR_NUM_THREADS="1"
    export MALLOC_ARENA_MAX="2"
  '';
  celeryPostValidationEnv = ''
    export VIDEO_POST_VALIDATION_JOB_MODE="celery"
  '';
  celeryInferenceEnv = ''
    export VIDEO_TEMPORAL_INFERENCE_JOB_MODE="celery"
    export VIDEO_TEMPORAL_INFERENCE_FRAME_SOURCE_MODE="stream"
    ${optionalString (cfg.runtime.inferenceWorker.cudaVisibleDevices != null) ''
      export CUDA_VISIBLE_DEVICES="${cfg.runtime.inferenceWorker.cudaVisibleDevices}"
    ''}
  '';
  celeryTrainingEnv = ''
    export MODEL_TRAINING_JOB_MODE="celery"
    export MODEL_TRAINING_STAGING_ROOT="${cfg.runtime.modelTrainingStagingRoot}"
    export CUDA_VISIBLE_DEVICES="${cfg.runtime.trainingWorker.cudaVisibleDevices}"
  '';
  mkRepoCeleryWorkerScript =
    {
      scriptName,
      hostname,
      queues,
      pool,
      extraEnv ? "",
    }:
    pkgs.writeShellScriptBin "${scriptName}" ''
      set -euo pipefail

      cd "${repoDir}"

      source "${lxAnnotateEnvHelpers}"
      lx_annotate_export_base_env
      lx_annotate_export_storage_env "${envDataDir}"
      lx_annotate_export_encryption_env
      lx_annotate_export_db_env
      lx_annotate_export_secret_key_env
      export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
      ${extraEnv}
      ${celeryWorkerResourceEnv}
      ${devenvSyncCompatExports}

      celery_worker_args=(
        -A lx_annotate.celery:app
        worker
        --loglevel=INFO
        --hostname="${hostname}@%h"
        --queues="${queues}"
        --concurrency="${toString pool.concurrency}"
        --prefetch-multiplier=1
        --max-tasks-per-child="${toString pool.maxTasksPerChild}"
      )

      exec devenv shell -- celery "''${celery_worker_args[@]}"
    '';
  mkWheelCeleryWorkerScript =
    {
      scriptName,
      hostname,
      queues,
      pool,
      extraEnv ? "",
    }:
    pkgs.writeShellScriptBin "${scriptName}" ''
      set -euo pipefail

      if [ -z ${lib.escapeShellArg wheelCeleryWorkerCommand} ]; then
        echo "ERROR: runtime.commands.celeryWorker must be set when wheel mode enables the Celery worker service."
        exit 1
      fi

      source "${lxAnnotateRuntimeLib}"
      source "${lxAnnotateEnvHelpers}"
      lx_annotate_export_wheel_service_env "${envDataDir}"
      ${extraEnv}
      ${celeryWorkerResourceEnv}
      export PATH="${runtimeWheelVenvPath}/bin:$PATH"

      if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
        echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
        exit 1
      fi

      export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
      export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
      wheel_celery_command=${lib.escapeShellArg wheelCeleryWorkerCommand}
      celery_worker_args=(
        --hostname="${hostname}@%h"
        --queues="${queues}"
        --concurrency="${toString pool.concurrency}"
        --prefetch-multiplier=1
        --max-tasks-per-child="${toString pool.maxTasksPerChild}"
      )
      printf -v celery_worker_args_shell '%q ' "''${celery_worker_args[@]}"
      exec "${pkgs.bash}/bin/bash" -lc "$wheel_celery_command $celery_worker_args_shell"
    '';
  runLocalCeleryWorkerScript = mkRepoCeleryWorkerScript {
    scriptName = celeryWorkerScriptName;
    hostname = "maintenance";
    queues = "${celeryMaintenanceQueueName},${celeryDefaultQueueName}";
    pool = cfg.runtime.workerPools.maintenance;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryWorkerWheelScript = mkWheelCeleryWorkerScript {
    scriptName = celeryWorkerScriptName;
    hostname = "maintenance";
    queues = "${celeryMaintenanceQueueName},${celeryDefaultQueueName}";
    pool = cfg.runtime.workerPools.maintenance;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryPipelineWorkerScript = mkRepoCeleryWorkerScript {
    scriptName = celeryPipelineWorkerScriptName;
    hostname = "pipeline";
    queues = celeryPipelineQueueName;
    pool = cfg.runtime.workerPools.pipeline;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryPipelineWorkerWheelScript = mkWheelCeleryWorkerScript {
    scriptName = celeryPipelineWorkerScriptName;
    hostname = "pipeline";
    queues = celeryPipelineQueueName;
    pool = cfg.runtime.workerPools.pipeline;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryFrameExtractionWorkerScript = mkRepoCeleryWorkerScript {
    scriptName = celeryFrameExtractionWorkerScriptName;
    hostname = "frame-extraction";
    queues = celeryFrameExtractionQueueName;
    pool = cfg.runtime.workerPools.frameExtraction;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryFrameExtractionWorkerWheelScript = mkWheelCeleryWorkerScript {
    scriptName = celeryFrameExtractionWorkerScriptName;
    hostname = "frame-extraction";
    queues = celeryFrameExtractionQueueName;
    pool = cfg.runtime.workerPools.frameExtraction;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryFfmpegWorkerScript = mkRepoCeleryWorkerScript {
    scriptName = celeryFfmpegWorkerScriptName;
    hostname = "ffmpeg-media";
    queues = celeryFfmpegMediaQueueName;
    pool = cfg.runtime.workerPools.ffmpeg;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryFfmpegWorkerWheelScript = mkWheelCeleryWorkerScript {
    scriptName = celeryFfmpegWorkerScriptName;
    hostname = "ffmpeg-media";
    queues = celeryFfmpegMediaQueueName;
    pool = cfg.runtime.workerPools.ffmpeg;
    extraEnv = celeryPostValidationEnv;
  };
  runLocalCeleryInferenceWorkerScript = mkRepoCeleryWorkerScript {
    scriptName = celeryInferenceWorkerScriptName;
    hostname = "inference";
    queues = celeryInferenceQueueName;
    pool = cfg.runtime.workerPools.inference;
    extraEnv = celeryInferenceEnv;
  };
  runLocalCeleryInferenceWorkerWheelScript = mkWheelCeleryWorkerScript {
    scriptName = celeryInferenceWorkerScriptName;
    hostname = "inference";
    queues = celeryInferenceQueueName;
    pool = cfg.runtime.workerPools.inference;
    extraEnv = celeryInferenceEnv;
  };
  runLocalCeleryTrainingWorkerScript = mkRepoCeleryWorkerScript {
    scriptName = celeryTrainingWorkerScriptName;
    hostname = "model-training";
    queues = celeryTrainingQueueName;
    pool = cfg.runtime.workerPools.training;
    extraEnv = celeryTrainingEnv;
  };
  runLocalCeleryTrainingWorkerWheelScript = mkWheelCeleryWorkerScript {
    scriptName = celeryTrainingWorkerScriptName;
    hostname = "model-training";
    queues = celeryTrainingQueueName;
    pool = cfg.runtime.workerPools.training;
    extraEnv = celeryTrainingEnv;
  };
  runLocalAcceptanceWheelScript = pkgs.writeShellScriptBin "${acceptanceScriptName}" ''
    set -euo pipefail

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_wheel_service_env "${envDataDir}"

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
        expected_device_id=${
          lib.escapeShellArg (
            if cfg.storageRelief.expectedDeviceId == null then "" else cfg.storageRelief.expectedDeviceId
          )
        }
        expected_device_part=${lib.escapeShellArg cfg.storageRelief.expectedDevicePart}
        expected_fs_uuid=${
          lib.escapeShellArg (
            if cfg.storageRelief.expectedFsUuid == null then "" else cfg.storageRelief.expectedFsUuid
          )
        }

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

  hubBackupScripts = import ./scripts/hub-backup.nix args;
  inherit (hubBackupScripts) runLocalHubBackupScript;

  encryptedDataScripts = import ./scripts/encrypted-data.nix args;
  inherit (encryptedDataScripts)
    lxAnnotateEncryptedDataMountScript
    lxAnnotateEncryptedDataUmountScript
    ;

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
      migrateVideoStreamableStorageScriptName
      ;
  };

  serviceOrdering = {
    fileMoverAfter = [
      loadBaseDataServiceName
      masterKeyCheckServiceName
    ];
    fileMoverWants = [ loadBaseDataServiceName ];
    fileMoverRequires = [
      loadBaseDataServiceName
      masterKeyCheckServiceName
    ];
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
      lxAnnotateEncryptedDataUmountScript
      ;
  };
}
