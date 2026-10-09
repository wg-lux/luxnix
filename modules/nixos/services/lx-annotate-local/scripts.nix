args@{
  pkgs,
  cfg,
  lxAnnotateRuntime,
  effectiveRuntimePackage,
  ...
}:
let

  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    ;
  inherit (runtime.paths)
    repoDir
    runtimeStorageRootPath
    runtimeStreamableVideoRootPath
    runtimeStreamableVideoRawRootPath
    runtimeStreamableVideoProcessedRootPath
    runtimeWheelVenvPath
    envDataDir
    ;
  inherit (runtime.env)
    envAnnotateDjangoSettingsModule
    ;
  inherit (runtime.runtime)
    useWheelRuntime
    pythonInterpreter
    ;
  envScripts = args.envContract or (import ./scripts/env.nix args);
  inherit (envScripts)
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
  migrateVideoStreamableStorageScriptName = "lx-annotate-migrate-video-streamable-storage";
  hlsMaterializationScriptName = "runLxAnnotateHlsMaterialization";
  repoVenvPythonPath = "${repoDir}/.devenv/state/venv/bin/python";
  repoLegacyVenvPythonPath = "${repoDir}/.venv/bin/python";
  wheelVenvPythonPath = "${runtimeWheelVenvPath}/bin/python";
  helperPythonPath = pythonInterpreter;
  loadBaseDataServiceName = "lx-annotate-load-base-data.service";
  masterKeyCheckServiceName = "lx-annotate-master-key-check.service";
  masterKeyCheckScriptName = "runLocalMasterKeyCheck";

  lxAnnotateRuntimeLib = pkgs.writeShellScript "lx-annotate-runtime-lib.sh" ''
        set -euo pipefail
        umask 027

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
          export LX_ANNOTATE_ENV_FILE="${repoDir}/.env"
        }

        require_file_backed_master_key() {
          local key_file="''${LX_ANNOTATE_MASTER_KEY_FILE:-}"

          if [ -n "''${LX_ANNOTATE_MASTER_KEY:-}" ]; then
            die "LX_ANNOTATE_MASTER_KEY must not be set in production; use the host-owned LX_ANNOTATE_MASTER_KEY_FILE secret handle."
          fi
          if [ -z "$key_file" ]; then
            die "LX_ANNOTATE_MASTER_KEY_FILE is not configured."
          fi
          if [ ! -f "$key_file" ] || [ ! -r "$key_file" ] || [ ! -s "$key_file" ]; then
            die "LX_ANNOTATE_MASTER_KEY_FILE is not a readable, non-empty regular file: $key_file"
          fi

          "${helperPythonPath}" - "$key_file" <<'PY'
    import base64
    import binascii
    import pwd
    import stat
    import sys
    from pathlib import Path

    key_path = Path(sys.argv[1])
    if not key_path.is_absolute() or key_path.is_symlink():
        raise SystemExit("Application master key must be an absolute, non-symlink file")
    key_stat = key_path.stat()
    key_mode = stat.S_IMODE(key_stat.st_mode)

    service_uid = pwd.getpwnam("${endoreg-service-user-name}").pw_uid
    if key_stat.st_uid not in {0, service_uid}:
        raise SystemExit("Application master key file must be owned by root or the service user")
    if not stat.S_ISREG(key_stat.st_mode) or key_mode & 0o077:
        raise SystemExit("Application master key must be a private regular file without group or other access")

    try:
        encoded_key = key_path.read_text(encoding="ascii").strip()
        decoded_key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
    except (UnicodeDecodeError, ValueError, binascii.Error) as exc:
        raise SystemExit(
            "Application master key file must contain URL-safe base64 key material"
        ) from exc

    if len(decoded_key) not in {16, 24, 32}:
        raise SystemExit(
            "Application master key must decode to 16, 24, or 32 bytes"
        )
    PY
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
            if [ ! -x "${repoVenvPythonPath}" ] || [ "$LOCK_HASH" != "$previousLockHash" ]; then
              log "uv deps changed or venv missing -> syncing..."
              eval "$SYNC_CMD" || warn "uv sync failed; continuing with existing environment."
              printf '%s\n' "$LOCK_HASH" > "$SYNC_STAMP"
            else
              log "uv deps unchanged -> skipping sync."
            fi
          fi
        }

        lx_annotate_repo_python() {
          if [ -x "${repoVenvPythonPath}" ]; then
            printf '%s\n' "${repoVenvPythonPath}"
            return 0
          fi
          if [ -x "${repoLegacyVenvPythonPath}" ]; then
            printf '%s\n' "${repoLegacyVenvPythonPath}"
            return 0
          fi
          die "lx-annotate repo Python runtime missing. Expected ${repoVenvPythonPath} or ${repoLegacyVenvPythonPath}."
        }

        run_django_command_with_python() {
          local python_bin="$1"
          shift
          "$python_bin" -m django "$@" --settings="${envAnnotateDjangoSettingsModule}"
        }

        run_repo_django_command() {
          local python_bin
          python_bin="$(lx_annotate_repo_python)"
          (
            cd "${repoDir}"
            run_django_command_with_python "$python_bin" "$@"
          )
        }

        ensure_wheel_runtime_installed() {
          "${effectiveRuntimePackage}/bin/lx-annotate-runtime-ensure"
        }

        run_installed_django_command() {
          local python_bin="$1"
          shift
          run_django_command_with_python "$python_bin" "$@"
        }
  '';

  lxAnnotateMigrateVideoStreamableStorageScript = pkgs.writeShellScriptBin "${migrateVideoStreamableStorageScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"

    log "Reconciling LX-Annotate video and PDF artifact paths and filenames..."
    if [ "${if useWheelRuntime then "true" else "false"}" = "true" ]; then
      source "${lxAnnotateEnvHelpers}"
      lx_annotate_export_wheel_service_env "${envDataDir}"
      ensure_wheel_runtime_installed
    else
      lx_annotate_export_runtime_env
      lx_annotate_activate_runtime
    fi
    export LX_RUNTIME_ROOT="${envDataDir}"
    exec ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate_media_storage "$@"
  '';

  runLocalHlsMaterializationScript = pkgs.writeShellScriptBin "${hlsMaterializationScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"

    explicit_artifact_kind="false"
    previous_arg=""
    for arg in "$@"; do
      if [ "$previous_arg" = "--artifact-kind" ]; then
        case "$arg" in
          raw|processed|both)
            ;;
          *)
            die "runLxAnnotateHlsMaterialization requires --artifact-kind raw, processed, or both."
            ;;
        esac
      fi
      case "$arg" in
        --force)
          die "runLxAnnotateHlsMaterialization refuses --force; use lx-annotate-manage materialize_video_hls manually for audited repair runs."
          ;;
        --inline)
          die "runLxAnnotateHlsMaterialization dispatches queued ffmpeg_media work; use lx-annotate-manage materialize_video_hls manually for inline retries."
          ;;
        --artifact-kind)
          explicit_artifact_kind="true"
          ;;
        --artifact-kind=raw|--artifact-kind=processed|--artifact-kind=both)
          explicit_artifact_kind="true"
          ;;
        --artifact-kind=*)
          die "runLxAnnotateHlsMaterialization requires --artifact-kind raw, processed, or both."
          ;;
      esac
      previous_arg="$arg"
    done

    if [ "$previous_arg" = "--artifact-kind" ]; then
      die "runLxAnnotateHlsMaterialization requires a value after --artifact-kind."
    fi

    if [ "${if useWheelRuntime then "true" else "false"}" = "true" ]; then
      source "${lxAnnotateEnvHelpers}"
      lx_annotate_export_wheel_service_env "${envDataDir}"
      require_file_backed_master_key
      ensure_wheel_runtime_installed
    else
      lx_annotate_export_runtime_env
      require_file_backed_master_key
      lx_annotate_activate_runtime
    fi

    run_hls_materialization() {
      local artifact_kind="$1"
      shift
      log "Dispatching $artifact_kind-video HLS materialization jobs..."
      ${effectiveRuntimePackage}/bin/lx-annotate-manage materialize_video_hls \
        --artifact-kind "$artifact_kind" --apply --json "$@"
    }

    if [ "$explicit_artifact_kind" = "true" ]; then
      log "Dispatching explicitly selected video HLS materialization jobs..."
      exec ${effectiveRuntimePackage}/bin/lx-annotate-manage materialize_video_hls --apply --json "$@"
    fi

    # Let the application finish its prioritized processed pass before raw HLS.
    # Separate invocations bypass its cross-artifact ordering and hash cache.
    run_hls_materialization both "$@"
  '';
  runLocalMasterKeyCheckScript = pkgs.writeShellScriptBin "${masterKeyCheckScriptName}" ''
    set -euo pipefail

    source "${lxAnnotateRuntimeLib}"
    if [ "${if useWheelRuntime then "true" else "false"}" = "true" ]; then
      source "${lxAnnotateEnvHelpers}"
      lx_annotate_export_wheel_service_env "${envDataDir}"
      require_file_backed_master_key
      ensure_wheel_runtime_installed
    else
      lx_annotate_export_runtime_env
      require_file_backed_master_key
      lx_annotate_activate_runtime
    fi
    install -d -m 0750 "${runtimeStorageRootPath}" "${runtimeStreamableVideoRootPath}" "${runtimeStreamableVideoRawRootPath}" "${runtimeStreamableVideoProcessedRootPath}"

    if [ "${if useWheelRuntime then "true" else "false"}" = "true" ]; then
      run_installed_django_command "${wheelVenvPythonPath}" verify_encrypted_storage
    else
      run_repo_django_command verify_encrypted_storage
    fi

    log "lx-annotate application master key check passed."
  '';

  runLocalDataRecoveryScript = pkgs.writeShellScriptBin "runLxAnnotateDataRecovery" ''
        set -euo pipefail
        umask 027
        target_dir="${envDataDir}"
        resolved_target_dir="$(${pkgs.coreutils}/bin/realpath -m "$target_dir")"
        marker_dir="$target_dir/logs"
        marker_file="$marker_dir/data_recovery_complete"
        repair_marker_file="$marker_dir/data_migration_repair_latest.log"
        # Bump this when managed-payload repair gains new eligibility or encryption semantics.
        repair_revision="v2"
        repair_completion_marker_file="$marker_dir/managed_payload_repair_$repair_revision"
        state_file="${cfg.dataRecovery.stateFile}"
        state_dir="$(${pkgs.coreutils}/bin/dirname "$state_file")"
        previous_effective_dir=""
        use_wheel_runtime="${if useWheelRuntime then "true" else "false"}"
        force_data_recovery="''${LX_ANNOTATE_FORCE_DATA_RECOVERY:-false}"
        force_managed_payload_repair="''${LX_ANNOTATE_FORCE_MANAGED_PAYLOAD_REPAIR:-false}"
        install -d -m 0750 "$target_dir" "$marker_dir" "$state_dir"

        if [ -f "$state_file" ]; then
          previous_effective_dir="$(${pkgs.gnugrep}/bin/grep '^LAST_EFFECTIVE_DATA_DIR=' "$state_file" | ${pkgs.coreutils}/bin/tail -n 1 | ${pkgs.coreutils}/bin/cut -d= -f2- || true)"
        fi

        if [ -n "$previous_effective_dir" ]; then
          resolved_previous_effective_dir="$(${pkgs.coreutils}/bin/realpath -m "$previous_effective_dir")"
        else
          resolved_previous_effective_dir=""
        fi

        recovery_already_current=false
        # Heavy legacy recovery is one-time work for a data root. It must not use the
        # payload-repair marker: repair logic can improve after legacy recovery is done.
        if [ "$resolved_previous_effective_dir" = "$resolved_target_dir" ] \
          && [ -f "$marker_file" ] \
          && ${pkgs.gnugrep}/bin/grep -q '^completed_at=' "$marker_file"; then
          recovery_already_current=true
        fi

        repair_already_current=false
        if [ -f "$repair_completion_marker_file" ] \
          && ${pkgs.gnugrep}/bin/grep -qx "repair_revision=$repair_revision" "$repair_completion_marker_file" \
          && ${pkgs.gnugrep}/bin/grep -q '^completed_at=' "$repair_completion_marker_file"; then
          repair_already_current=true
        fi

        run_heavy_recovery=true
        if [ "$recovery_already_current" = "true" ] && [ "$force_data_recovery" != "true" ]; then
          run_heavy_recovery=false
        fi

        run_managed_payload_repair=true
        if [ "$run_heavy_recovery" = "false" ] \
          && [ "$repair_already_current" = "true" ] \
          && [ "$force_managed_payload_repair" != "true" ]; then
          run_managed_payload_repair=false
        fi

        if [ "$run_heavy_recovery" = "false" ] && [ "$run_managed_payload_repair" = "false" ]; then
          echo "Data recovery and managed payload repair revision $repair_revision are already current for $resolved_target_dir."
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

        if [ "$use_wheel_runtime" = "true" ]; then
          ensure_wheel_runtime_installed
          if [ -x "${wheelVenvPythonPath}" ]; then
            echo "Applying Django migrations before data recovery helper commands."
            run_installed_django_command "${wheelVenvPythonPath}" check_migration_compatibility
            run_installed_django_command "${wheelVenvPythonPath}" migrate --noinput
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

        write_repair_failure() {
          local repair_output="$1"
          ${pkgs.coreutils}/bin/rm -f "$repair_completion_marker_file"
          {
            printf 'repair_revision=%s\n' "$repair_revision"
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
          local repair_completion_tmp="$repair_completion_marker_file.tmp"

          # A forced retry must not leave an old successful revision marker behind.
          ${pkgs.coreutils}/bin/rm -f "$repair_completion_marker_file"

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
            printf 'repair_revision=%s\n' "$repair_revision"
            printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
            printf 'target_dir=%s\n' "$target_dir"
            printf '%s\n' "$repair_output"
          } > "$repair_marker_file"
          chmod 0640 "$repair_marker_file"
          {
            printf 'repair_revision=%s\n' "$repair_revision"
            printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
            printf 'target_dir=%s\n' "$target_dir"
          } > "$repair_completion_tmp"
          ${pkgs.coreutils}/bin/mv "$repair_completion_tmp" "$repair_completion_marker_file"
          chmod 0640 "$repair_completion_marker_file"
          echo "Managed payload repair revision $repair_revision completed; log=$repair_marker_file marker=$repair_completion_marker_file"
          return 0
        }

        migration_helper_python=""
        if [ "$use_wheel_runtime" = "true" ]; then
          if [ -x "${wheelVenvPythonPath}" ]; then
            migration_helper_python="${wheelVenvPythonPath}"
          fi
        elif [ -f "${repoDir}/scripts/migrate_data_dir.py" ] && [ -x "${repoVenvPythonPath}" ]; then
          migration_helper_python="${repoVenvPythonPath}"
        fi

        if [ "$run_heavy_recovery" = "true" ]; then
        if [ -n "$previous_effective_dir" ]; then
          if [ "$resolved_previous_effective_dir" != "$resolved_target_dir" ]; then
            sync_source_dir "$previous_effective_dir" "previous effective data dir"
          else
            echo "Configured data dir unchanged since last successful recovery: $resolved_target_dir"
          fi
        else
          echo "No previous effective data dir recorded in $state_file"
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

        if [ -n "$migration_helper_python" ]; then
          echo "Marking migration-created upload job source files as cleanup-eligible after data recovery."
          if [ "$use_wheel_runtime" = "true" ]; then
            run_installed_django_command "$migration_helper_python" migration_mark_eligible --apply || {
              echo "WARNING: migration_mark_eligible failed; continuing data recovery startup path." >&2
            }
          else
            cd "${repoDir}"
            "$migration_helper_python" "${repoDir}/manage.py" migration_mark_eligible --apply || {
              echo "WARNING: migration_mark_eligible failed; continuing data recovery startup path." >&2
            }
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
          echo "ERROR: cannot complete upload-job recovery; Django helper python is unavailable." >&2
          exit 1
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
        else
          echo "Data recovery already completed for $resolved_target_dir; skipping heavy legacy recovery."
        fi

        if [ "$run_managed_payload_repair" = "true" ]; then
          repair_managed_runtime_payloads "$migration_helper_python"
        else
          echo "Managed payload repair revision $repair_revision is already current; skipping."
        fi
  '';

in
{
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
      lxAnnotateMigrateVideoStreamableStorageScript
      runLocalDataRecoveryScript
      runLocalHlsMaterializationScript
      runLocalMasterKeyCheckScript
      ;
  };
}
