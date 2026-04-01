args@{ lib, ... }:
with lib;
with lib.luxnix;
with args;
let
  makeBin = "${pkgs.gnumake}/bin/make";
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
      export NGINX_PROTECTED_MEDIA_URL="/protected_media/"

      export DJANGO_ALLOWED_HOSTS="${envAllowedHosts}"
      export ALLOWED_HOSTS="${envAllowedHosts}"
      export DJANGO_CORS_ALLOWED_ORIGINS="${envCorsAllowedOrigins}"
      export DJANGO_CSRF_TRUSTED_ORIGINS="${envCorsAllowedOrigins}"
    }

    lx_annotate_export_storage_env() {
      local data_root="$1"
      export DATA_DIR="$data_root"
      export LX_ANNOTATE_ENCRYPTED_DATA_DIR="$data_root"
      export STORAGE_DIR="$data_root"
      export IO_DIR="$data_root"
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
  startScriptName = "lx-annotate-start";
  bootstrapScriptName = "lx-annotate-bootstrap";

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
      if [ -f "${repoDir}/.devenv/state/venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${repoDir}/.devenv/state/venv/bin/activate"
      elif [ -f "${repoDir}/.venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${repoDir}/.venv/bin/activate"
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

    ensure_runtime_static_root() {
      install -d -m 0775 "${staticRootPath}"
      install -d -m 0775 "${staticRootPath}/.vite"
      chown -R "${endoreg-service-user-name}:${endoreg-service-group-name}" "${staticRootPath}"

      if [ -L "${repoStaticRootPath}" ]; then
        ln -sfn "${staticRootPath}" "${repoStaticRootPath}"
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

      ln -sfn "${staticRootPath}" "${repoStaticRootPath}"
    }

    normalize_runtime_static_root_permissions() {
      if [ ! -d "${staticRootPath}" ]; then
        return 0
      fi

      chown -R "${endoreg-service-user-name}:${endoreg-service-group-name}" "${staticRootPath}"
      find "${staticRootPath}" -type d -exec chmod 0755 {} +
      find "${staticRootPath}" -type f -exec chmod 0644 {} +
    }

    write_systemd_env_file() {
      install -d -m 0750 "${runtimeRootPath}"
      cat > "${envSystemdFilePath}" <<EOF
HOME_DIR=${endoreg-service-user-home}
DATA_DIR=${envDataDir}
LX_ANNOTATE_ENCRYPTED_DATA_DIR=${envDataDir}
LX_ANNOTATE_DATA_DIR=${envDataDir}
CONF_DIR=${envConfDir}
CONF_TEMPLATE_DIR=${envConfTemplateDir}
WORKING_DIR=${repoDir}
DJANGO_STATIC_ROOT=${djangoStaticRootPath}
STORAGE_DIR=${envDataDir}
IO_DIR=${envDataDir}
SERVE_WITH_NGINX=true
NGINX_PROTECTED_MEDIA_URL=/protected_media/
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
EOF
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

    mark_current_checkout_good() {
      local current_revision=""
      current_revision="$(current_revision_or_unknown)"
      if [ "$current_revision" = "unknown" ]; then
        die "Cannot mark checkout healthy because HEAD is unresolved."
      fi
      install -d -m 0750 "${runtimeRootPath}"
      printf '%s\n' "$current_revision" > "$(last_known_good_revision_file)"
      chmod 0640 "$(last_known_good_revision_file)" 2>/dev/null || true
      log "Marked checkout as last-known-good: $current_revision"
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
    ensure_runtime_static_root
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime
    write_secretspec_config
    printf '%s\n' "${envDjangoEnv}" > "${repoDir}/.mode"
    chmod 600 "${repoDir}/.mode" 2>/dev/null || true
    align_repo_env_file
    write_systemd_env_file
  '';

  lxAnnotateBuildScript = pkgs.writeShellScriptBin "${buildScriptName}" ''
    set -euo pipefail
    source "${lxAnnotateRuntimeLib}"
    lx_annotate_export_runtime_env
    lx_annotate_activate_runtime

    if [ "''${DJANGO_STATIC_ROOT%/}" = "${viteSourcePath}" ]; then
      die "DJANGO_STATIC_ROOT points to Vite source assets (${viteSourcePath})."
    fi

    log "Building frontend assets into ${djangoStaticRootPath}..."
    if command -v devenv >/dev/null 2>&1; then
      devenv shell -- vue-build || warn "Frontend build failed; validating existing Vite manifest."
    else
      die "devenv is required for frontend builds."
    fi
    normalize_runtime_static_root_permissions
    if ! vite_manifest_points_to_existing_asset "${djangoStaticRootPath}/.vite/manifest.json"; then
      die "Vite manifest is missing/invalid after frontend build preparation."
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


    python manage.py load_base_db_data


    if [ "$current_revision" != "$last_bootstrap_revision" ]; then
      printf '%s\n' "$current_revision" > "$bootstrap_stamp_file"
      chmod 600 "$bootstrap_stamp_file" 2>/dev/null || true
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
        die "Fallback checkout restored, but static assets are not usable."
      fi
    }

    if \
      run_stage "sync" "${lxAnnotateSyncScript}/bin/${syncScriptName}" && \
      run_stage "prepare" "${lxAnnotatePrepareScript}/bin/${prepareScriptName}" && \
      run_stage "build" "${lxAnnotateBuildScript}/bin/${buildScriptName}" && \
      run_stage "migrate" "${lxAnnotateMigrateScript}/bin/${migrateScriptName}"
    then
      mark_current_checkout_good
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
      die "Vite manifest is missing/invalid before server start."
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
  runLocalLxAnnotateWheelScript = pkgs.writeShellScriptBin "${scriptName}" ''
    set -euo pipefail

    if [ -z "${wheelFilePath}" ]; then
      echo "ERROR: services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set in wheel mode."
      exit 1
    fi

    install -d -m 0750 "${runtimeRootPath}" "${runtimeWheelRootPath}" "${runtimeWheelVenvPath}" "${envConfDir}" "${envDataDir}"
    install -d -m 0775 "${runtimeStaticRootPath}" "${runtimeStaticRootPath}/.vite"

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
    export WORKING_DIR="${runtimeWorkingDir}"
    export HOME_DIR="${endoreg-service-user-home}"
    export XDG_DATA_HOME="${runtimeRootPath}"
    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${envDataDir}"
    export LX_ANNOTATE_DATA_DIR="${envDataDir}"
    export LX_ANNOTATE_DEFAULT_CENTER="${envDefaultCenter}"
    export TESSDATA_PREFIX="${cfg.runtime.tessdataPrefix}"
    export PYTORCH_ALLOC_CONF="${cfg.runtime.pytorchAllocConf}"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    cat > "${envSystemdFilePath}" <<EOF
HOME_DIR=${endoreg-service-user-home}
DATA_DIR=${envDataDir}
LX_ANNOTATE_ENCRYPTED_DATA_DIR=${envDataDir}
CONF_DIR=${envConfDir}
CONF_TEMPLATE_DIR=${envConfTemplateDir}
WORKING_DIR=${runtimeWorkingDir}
DJANGO_STATIC_ROOT=${djangoStaticRootPath}
STORAGE_DIR=${envDataDir}
IO_DIR=${envDataDir}
SERVE_WITH_NGINX=true
NGINX_PROTECTED_MEDIA_URL=/protected_media/
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
DJANGO_SETTINGS_MODULE=lx_annotate.settings.settings_prod
DJANGO_SETTINGS_MODULE_PRODUCTION=lx_annotate.settings.settings_prod
DJANGO_ENV=production
XDG_DATA_HOME=${runtimeRootPath}
LX_ANNOTATE_DATA_DIR=${envDataDir}
TESSDATA_PREFIX=${cfg.runtime.tessdataPrefix}
PYTORCH_ALLOC_CONF=${cfg.runtime.pytorchAllocConf}
${optionalString (cfg.runtime.masterKeyFile != null) "LX_ANNOTATE_MASTER_KEY_FILE=${toString cfg.runtime.masterKeyFile}"}
EOF

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      "${pythonInterpreter}" -m venv "${runtimeWheelVenvPath}"
    fi

    wheel_hash="$(${pkgs.coreutils}/bin/sha256sum "${wheelFilePath}" | ${pkgs.coreutils}/bin/cut -d ' ' -f1)"
    wheelhouse_path="${optionalString (cfg.runtime.wheelhousePath != null) (toString cfg.runtime.wheelhousePath)}"
    wheelhouse_hash="no-wheelhouse"
    pip_install_args=""
    wheel_install_stamp_file="${runtimeRootPath}/.wheel-install.sha256"
    installed_hash="$(${pkgs.coreutils}/bin/cat "$wheel_install_stamp_file" 2>/dev/null || true)"
    canonical_wheel_name="$(${pkgs.coreutils}/bin/basename "${wheelFilePath}" | ${pkgs.gnused}/bin/sed -E 's/^[a-z0-9]{32}-//')"
    staged_wheel_path="${runtimeRootPath}/$canonical_wheel_name"

    if [ -n "$wheelhouse_path" ]; then
      if [ ! -d "$wheelhouse_path" ]; then
        echo "ERROR: Configured runtime.wheelhousePath does not exist: $wheelhouse_path"
        exit 1
      fi
      wheelhouse_hash="$(
        (
          ${pkgs.findutils}/bin/find "$wheelhouse_path" -maxdepth 1 -type f \
            \( -name '*.whl' -o -name '*.tar.gz' -o -name '*.zip' \) -print0 \
          | ${pkgs.coreutils}/bin/sort -z \
          | ${pkgs.findutils}/bin/xargs -0 -r ${pkgs.coreutils}/bin/sha256sum
        ) | ${pkgs.coreutils}/bin/sha256sum | ${pkgs.coreutils}/bin/cut -d ' ' -f1
      )"
      pip_install_args="--no-index --find-links $wheelhouse_path"
    fi

    install_hash="$(
      printf '%s\n%s\n%s\n' \
        "$wheel_hash" \
        "$wheelhouse_hash" \
        "${pythonInterpreter}" \
      | ${pkgs.coreutils}/bin/sha256sum \
      | ${pkgs.coreutils}/bin/cut -d ' ' -f1
    )"

    if [ "$install_hash" != "$installed_hash" ]; then
      ${pkgs.coreutils}/bin/install -m 0640 "${wheelFilePath}" "$staged_wheel_path"
      # Install only when the app wheel, wheelhouse, or Python interpreter changed.
      # If a local wheelhouse is configured, keep the install fully offline.
      # shellcheck disable=SC2086
      "${runtimeWheelVenvPath}/bin/pip" install --upgrade --force-reinstall $pip_install_args "$staged_wheel_path"
      printf '%s\n' "$install_hash" > "$wheel_install_stamp_file"
      chmod 0640 "$wheel_install_stamp_file" 2>/dev/null || true
    fi

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
    if [ -e "${djangoStaticRootPath}" ] && [ ! -L "${djangoStaticRootPath}" ]; then
      rm -rf "${djangoStaticRootPath}"
    fi
    ln -sfn "${runtimeStaticRootPath}" "${djangoStaticRootPath}"
    ${pkgs.coreutils}/bin/chown -R "${endoreg-service-user-name}:${endoreg-service-group-name}" "${runtimeStaticRootPath}"
    ${pkgs.findutils}/bin/find "${runtimeStaticRootPath}" -type d -exec ${pkgs.coreutils}/bin/chmod 0755 {} +
    ${pkgs.findutils}/bin/find "${runtimeStaticRootPath}" -type f -exec ${pkgs.coreutils}/bin/chmod 0644 {} +

    bootstrap_stamp_file="${envConfDir}/.bootstrap-wheel"
    last_bootstrap_hash="$(${pkgs.coreutils}/bin/cat "$bootstrap_stamp_file" 2>/dev/null || true)"

    "${runtimeWheelVenvPath}/bin/python" -m django migrate --settings=lx_annotate.settings.settings_prod --noinput
    if "${runtimeWheelVenvPath}/bin/python" "${baseDataCheckScript}" >/dev/null 2>&1; then
      echo "Base data already present; skipping load_base_db_data."
    elif [ "$install_hash" != "$last_bootstrap_hash" ]; then
      "${runtimeWheelVenvPath}/bin/python" -m django load_base_db_data --settings=lx_annotate.settings.settings_prod
      "${runtimeWheelVenvPath}/bin/python" "${baseDataCheckScript}" >/dev/null 2>&1 || {
        echo "ERROR: Base data load completed but verification still failed."
        exit 1
      }
      printf '%s\n' "$install_hash" > "$bootstrap_stamp_file"
      chmod 0640 "$bootstrap_stamp_file" 2>/dev/null || true
    else
      echo "Wheel unchanged and base data still missing; refusing implicit reload."
      exit 1
    fi

    exec "${runtimeWheelVenvPath}/bin/daphne" -b "${envDjangoHost}" -p "${envDjangoPort}" lx_annotate.asgi:application
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
    export WATCHER_PREANONYMIZED_DIR="${envDataDir}/import/preanonymized_import"
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

    if [ -z "${cfg.runtime.commands.fileWatcher or ""}" ]; then
      echo "ERROR: runtime.commands.fileWatcher must be set when wheel mode enables the watcher service."
      exit 1
    fi

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export WORKING_DIR="${runtimeWorkingDir}"
    export HOME_DIR="${endoreg-service-user-home}"
    export XDG_DATA_HOME="${runtimeRootPath}"
    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${envDataDir}"
    export LX_ANNOTATE_DATA_DIR="${envDataDir}"
    export WATCHER_PREANONYMIZED_DIR="${envDataDir}/import/preanonymized_import"
    export TESSDATA_PREFIX="${cfg.runtime.tessdataPrefix}"
    export PYTORCH_ALLOC_CONF="${cfg.runtime.pytorchAllocConf}"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    exec "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg (cfg.runtime.commands.fileWatcher or "")}
  '';
  runLocalSapImportScript = pkgs.writeShellScriptBin "runLocalSapImport" ''
    set -euo pipefail

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT="${djangoStaticRootPath}"
    export WATCHER_PREANONYMIZED_DIR="${envDataDir}/import/preanonymized_import"
    ${devenvSyncCompatExports}

    sap_drop_dir="${envDataDir}/import/sap_import"
    sap_processed_dir="${envDataDir}/import/sap_import_processed"
    sap_failed_dir="${envDataDir}/import/sap_import_failed"
    mkdir -p "$sap_drop_dir" "$sap_processed_dir" "$sap_failed_dir" "${envDataDir}/import/preanonymized_import"

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

      cd "${repoDir}"
      VENV_PYTHON="${repoDir}/.devenv/state/venv/bin/python"
      if [ ! -x "$VENV_PYTHON" ]; then
        echo "ERROR: repo venv missing at $VENV_PYTHON"
        exit 1
      fi

      if secretspec run --provider env "$VENV_PYTHON" manage.py import_sap_ish_zip "$zip_path" --output_dir "${envDataDir}/import/preanonymized_import"; then
        ${pkgs.coreutils}/bin/mv "$zip_path" "$sap_processed_dir/$zip_name"
      else
        echo "SAP import failed for $zip_path"
        ${pkgs.coreutils}/bin/mv "$zip_path" "$sap_failed_dir/$zip_name"
      fi
    done
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
      export STORAGE_DIR="$exportFramesStorageRoot"
      export IO_DIR="$exportFramesStorageRoot"
      export DATA_DIR="$exportFramesStorageRoot"
      exec "${makeBin}" REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" start-export
    fi

    exec devenv shell -- bash -c "STORAGE_DIR='$exportFramesStorageRoot' IO_DIR='$exportFramesStorageRoot' DATA_DIR='$exportFramesStorageRoot' export-frames"
  '';
  runLocalExportFramesWheelScript = pkgs.writeShellScriptBin "${exportFramesScriptName}" ''
    set -euo pipefail

    if [ -z "${cfg.runtime.commands.exportFrames or ""}" ]; then
      echo "ERROR: runtime.commands.exportFrames must be set when wheel mode enables the export service."
      exit 1
    fi

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
    export WORKING_DIR="${runtimeWorkingDir}"
    export HOME_DIR="${endoreg-service-user-home}"
    export XDG_DATA_HOME="${runtimeRootPath}"
    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="$exportFramesStorageRoot"
    export LX_ANNOTATE_DATA_DIR="$exportFramesStorageRoot"
    export TESSDATA_PREFIX="${cfg.runtime.tessdataPrefix}"
    export PYTORCH_ALLOC_CONF="${cfg.runtime.pytorchAllocConf}"
    export PATH="${runtimeWheelVenvPath}/bin:$PATH"
    export STORAGE_DIR="$exportFramesStorageRoot"
    export IO_DIR="$exportFramesStorageRoot"
    export DATA_DIR="$exportFramesStorageRoot"

    mkdir -p "$exportFramesStorageRoot/export/frames"

    if [ ! -x "${runtimeWheelVenvPath}/bin/python" ]; then
      echo "ERROR: Wheel virtualenv missing at ${runtimeWheelVenvPath}."
      exit 1
    fi

    export LX_ANNOTATE_WHEEL_VENV="${runtimeWheelVenvPath}"
    export LX_ANNOTATE_WHEEL_APP_ROOT="${runtimeWheelRootPath}"
    exec "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg (cfg.runtime.commands.exportFrames or "")}
  '';

  runLocalDataRecoveryScript = pkgs.writeShellScriptBin "runLxAnnotateDataRecovery" ''
    set -euo pipefail

    target_dir="${envDataDir}"
    resolved_target_dir="$(${pkgs.coreutils}/bin/realpath -m "$target_dir")"
    marker_dir="$target_dir/logs"
    marker_file="$marker_dir/data_recovery_complete"
    state_file="${cfg.dataRecovery.stateFile}"
    state_dir="$(${pkgs.coreutils}/bin/dirname "$state_file")"
    previous_effective_dir=""
    mkdir -p "$target_dir" "$marker_dir" "$state_dir"

    source "${lxAnnotateEnvHelpers}"
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_encryption_env
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env

    if [ -f "$state_file" ]; then
      previous_effective_dir="$(${pkgs.gnugrep}/bin/grep '^LAST_EFFECTIVE_DATA_DIR=' "$state_file" | ${pkgs.coreutils}/bin/tail -n 1 | ${pkgs.coreutils}/bin/cut -d= -f2- || true)"
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
        --chown=${endoreg-service-user-name}:${endoreg-service-group-name} \
        "$source_root/" "$target_dir/"
    }

    if [ -n "$previous_effective_dir" ]; then
      resolved_previous_effective_dir="$(${pkgs.coreutils}/bin/realpath -m "$previous_effective_dir")"
      if [ "$resolved_previous_effective_dir" != "$resolved_target_dir" ]; then
        sync_source_dir "$previous_effective_dir" "previous effective data dir"
      else
        echo "Configured data dir unchanged since last successful recovery: $resolved_target_dir"
      fi
    else
      echo "No previous effective data dir recorded in $state_file"
    fi

    if [ -x "${repoDir}/.devenv/state/venv/bin/python" ] && [ -f "${repoDir}/scripts/migrate_data_dir.py" ]; then
      echo "Running lx-annotate repo migration helper into $target_dir"
      cd "${repoDir}"
      "${repoDir}/.devenv/state/venv/bin/python" "${repoDir}/scripts/migrate_data_dir.py" \
        --repo-root "${repoDir}" \
        --target "$target_dir" \
        --allow-merge
    else
      echo "Migration helper unavailable; falling back to compatibility rsync."
      sync_source_dir "${cfg.dataRecovery.legacyDataDir}" "legacy repo data"
      sync_source_dir "${cfg.dataRecovery.legacyMediaDir}" "legacy media"
    fi

    {
      printf 'LAST_EFFECTIVE_DATA_DIR=%s\n' "$resolved_target_dir"
      printf 'UPDATED_AT=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)"
    } > "$state_file.tmp"
    ${pkgs.coreutils}/bin/mv "$state_file.tmp" "$state_file"
    chown "${endoreg-service-user-name}:${endoreg-service-group-name}" "$state_file"
    chmod 0640 "$state_file"

    printf 'completed_at=%s\n' "$(${pkgs.coreutils}/bin/date --iso-8601=seconds)" > "$marker_file"
    chown "${endoreg-service-user-name}:${endoreg-service-group-name}" "$marker_file"
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

    chown "${endoreg-service-user-name}:${endoreg-service-group-name}" "$marker_file"
    chmod 0640 "$marker_file"

    echo "Cleanup completed. moved=$moved_count skipped=$skipped_count archive=$archive_root"
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

in {
  inherit
    makeBin
    lxAnnotateEnvHelpers
    lxAnnotateSyncScript
    lxAnnotatePrepareScript
    lxAnnotateBuildScript
    lxAnnotateMigrateScript
    lxAnnotateBootstrapScript
    runLocalLxAnnotateStartScript
    runLocalLxAnnotateScript
    runLocalLxAnnotateWheelScript
    watcherScriptName
    runLocalFileWatcherScript
    runLocalFileWatcherWheelScript
    runLocalSapImportScript
    runLocalExportFramesScript
    runLocalExportFramesWheelScript
    runLocalDataRecoveryScript
    runLocalDataCleanupScript
    runLocalHubBackupScript
    lxAnnotateEncryptedDataMountScript
    lxAnnotateEncryptedDataUmountScript;
}
