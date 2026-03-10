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
    sslDir = "/var/lib/lx-annotate/ssl";
    certPath = "/var/lib/lx-annotate/ssl/lx-annotate-selfsigned.crt";
    keyPath = "/var/lib/lx-annotate/ssl/lx-annotate-selfsigned.key";
  } config;

  defaultSslCertificatePath = sslCfg.certPath;
  defaultSslKeyPath = sslCfg.keyPath;

  adminName = config.user.admin.name;
  scriptName = "runLocalLxAnnotate";
  exportFramesScriptName = "runLocalExportFrames";

  # Use configuration options from new structure
  gitURL = cfg.source.url;
  repoDirName = "lx-annotate";
  branchName = cfg.source.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  endoreg-service-group-name = config.user.endoreg-service-user.group;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";
  staticRootPath = "${repoDir}/staticfiles";
  viteSourcePath = "${repoDir}/static";

  # Environment variable configuration from django submodule
  envDataDir = "${repoDir}/${cfg.django.dataDir}";
  envConfDir = "${repoDir}/${cfg.django.confDir}";
  makeCacheDir = "${envConfDir}/make-cache";
  envConfTemplateDir = "${repoDir}/${cfg.django.confTemplateDir}";
  envDjangoModule = cfg.django.djangoModule;
  envHttpProtocol =
    if cfg.django.httpProtocol != "http" then
      cfg.django.httpProtocol
    else
      (if cfg.django.useHttps then "https" else "http");
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

  makeAbsolute = path: if lib.hasPrefix "/" path then path else "${repoDir}/${path}";

  envAssetDir = makeAbsolute cfg.django.assetDir;
  envStaticUrl = cfg.django.staticUrl;
  envMediaUrl = cfg.django.mediaUrl;
  envRunVideoTests = if cfg.django.runVideoTests then "true" else "false";
  envSkipExpensiveTests = if cfg.django.skipExpensiveTests then "true" else "false";
  envViteEnableDebug = if cfg.debug.enable then "true" else "false";

  settingsProfile = cfg.django.settingsProfile;
  envIsCentralNode = cfg.django.extraSettings.IS_CENTRAL_NODE or false;
  envAnnotateDjangoSettingsModule = "lx_annotate.settings.settings_prod";
  envDjangoEnv = "production";
  envCentralNodeFlag = if envIsCentralNode || settingsProfile == "central" then "true" else "false";

  # Default center from django extraSettings
  envDefaultCenter = cfg.django.extraSettings.DEFAULT_CENTER or "university_hospital_wuerzburg";
  exportFramesStorageRootDefault = config.roles.endoreg-client.paths.storagePersistingMountPoint;
  mkDjangoOptions = import ../../lib/django-options.nix { inherit lib; };
  makeBin = "${pkgs.gnumake}/bin/make";
  lxAnnotateEnvHelpers = pkgs.writeShellScript "lx-annotate-env-helpers.sh" ''
    lx_annotate_export_base_env() {
      export DJANGO_SECRET_KEY_FILE="${cfg.django.djangoSecretKeyFile}"
      export OIDC_RP_CLIENT_SECRET_FILE="${cfg.django.keycloakSecretFile}"

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

      export DJANGO_ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
      export ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
      export DJANGO_CORS_ALLOWED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
      export DJANGO_CSRF_TRUSTED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
    }

    lx_annotate_export_storage_env() {
      local data_root="$1"
      export DATA_DIR="$data_root"
      export STORAGE_DIR="$data_root"
      export IO_DIR="$data_root"
    }

    lx_annotate_export_django_paths_env() {
      export STATIC_URL="${envStaticUrl}"
      export MEDIA_URL="${envMediaUrl}"
      export ASSET_DIR="${envAssetDir}"
    }

    lx_annotate_export_db_env() {
      local db_pwd
      db_pwd="$(tr -d '\n' < ${envConfDir}/db_pwd 2>/dev/null || true)"
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
      django_secret_key="$(tr -d '\n' < ${cfg.django.djangoSecretKeyFile} 2>/dev/null || true)"
      export DJANGO_SECRET_KEY="$django_secret_key"
    }

    lx_annotate_export_oidc_env() {
      
      local oidc_client_secret
      export OIDC_RP_CLIENT_ID="${cfg.django.keycloakClientId}"
      oidc_client_secret="$(tr -d '\n' < ${cfg.django.keycloakSecretFile} 2>/dev/null || true)"
      export OIDC_RP_CLIENT_SECRET="$oidc_client_secret"
    }
  '';

  # Compat exports for lx-annotate/devenv.nix shellHook, which expects these vars.
  devenvSyncCompatExports = ''
    export SYNC_CMD="uv sync --extra dev --extra docs"
    export SYNC_STAMP=".devenv/state/.uv-sync.stamp"
    mkdir -p "$(dirname "$SYNC_STAMP")"
    if [ -f "uv.lock" ] && [ -f "pyproject.toml" ]; then
      export LOCK_HASH="$(${pkgs.coreutils}/bin/sha256sum uv.lock pyproject.toml 2>/dev/null | ${pkgs.coreutils}/bin/sha256sum | ${pkgs.coreutils}/bin/cut -d ' ' -f1)"
    else
      export LOCK_HASH=""
    fi
  '';

  runLocalLxAnnotateScript = pkgs.writeShellScriptBin "${scriptName}" ''
        set -euo pipefail

        # Debug mode flag
        DEBUG_MODE=${if cfg.debug.enable then "true" else "false"}

        echo "Starting LxAnnotate service..."
        echo "Repository: ${gitURL}"
        echo "Branch: ${branchName}"

        # Clone or update repository
        if [ -d "${repoDir}" ] && [ ! -d "${repoDir}/.git" ]; then
          echo "WARNING: Target directory exists but is not a git repository. Removing it."
          rm -rf "${repoDir}"
        fi
        if [ ! -d ${repoDir} ]; then
          echo "Cloning repository..."
          git clone -b ${branchName} ${gitURL} ${repoDir}
        fi

        cd ${repoDir}
        direnv allow
        mkdir -p ${envConfDir} ${makeCacheDir}

        ensure_clean_latest_checkout() {
          local branch="${branchName}"
          local remote="origin"
          local remote_head=""
          local local_head=""

          echo "Ensuring checkout matches $remote/$branch..."
          git fetch "$remote" "$branch" || {
            echo "ERROR: Failed to fetch $remote/$branch."
            return 1
          }

          if ! git show-ref --verify --quiet "refs/remotes/$remote/$branch"; then
            echo "ERROR: Remote branch $remote/$branch not found."
            return 1
          fi

          if git show-ref --verify --quiet "refs/heads/$branch"; then
            git checkout "$branch" || return 1
          else
            git checkout -B "$branch" "$remote/$branch" || return 1
          fi

          remote_head="$(git rev-parse --verify "$remote/$branch" 2>/dev/null || true)"
          local_head="$(git rev-parse --verify HEAD 2>/dev/null || true)"
          if [ -z "$remote_head" ] || [ -z "$local_head" ]; then
            echo "ERROR: Unable to resolve git revision for checkout verification."
            return 1
          fi

          if [ "$local_head" != "$remote_head" ]; then
            echo "Local checkout is not at $remote/$branch; forcing hard reset to $remote_head."
            git reset --hard "$remote_head" || return 1
          fi

          if [ -d .make-cache ]; then
            git clean -fd -- .make-cache >/dev/null 2>&1 || true
          fi

          local_head="$(git rev-parse --verify HEAD 2>/dev/null || true)"
          if [ "$local_head" != "$remote_head" ]; then
            echo "ERROR: Checkout still differs from $remote/$branch after sync."
            return 1
          fi

          echo "Repository synced to commit $local_head on branch $branch."
        }

        if [ -f Makefile ]; then
          echo "Using Makefile repository sync targets..."
          if git ls-files --error-unmatch .make-cache/migrations.sha256 >/dev/null 2>&1; then
            if ! git diff --quiet -- .make-cache/migrations.sha256; then
              echo "Resetting tracked cache file .make-cache/migrations.sha256 before repository sync."
              git show HEAD:.make-cache/migrations.sha256 > .make-cache/migrations.sha256 || true
            fi
          fi
          ${
            if cfg.source.updateOnBoot then
              ''
                ${makeBin} REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" BRANCH="${branchName}" GIT_URL="${gitURL}" REMOTE="origin" update || {
                  echo "WARNING: Repository update failed; continuing with current checkout."
                }
                ensure_clean_latest_checkout || { echo "ERROR: Could not sync to latest origin/${branchName}."; exit 1; }
              ''
            else
              ''
                ${makeBin} REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" BRANCH="${branchName}" GIT_URL="${gitURL}" REMOTE="origin" setup
              ''
          }
        else
          echo "Makefile not found, using legacy git workflow."
          ${
            if cfg.source.updateOnBoot then
              ''
                echo "Updating repository..."
                git fetch origin ${branchName} || { echo "ERROR: Failed to fetch from origin"; exit 1; }
              ''
            else
              ''
                echo "Repository update disabled"
              ''
          }

          echo "Checking out branch: ${branchName}"
          if git show-ref --verify --quiet refs/heads/${branchName}; then
            git checkout ${branchName} || { echo "ERROR: Checkout failed"; exit 1; }
          elif git show-ref --verify --quiet refs/remotes/origin/${branchName}; then
            git checkout -b ${branchName} origin/${branchName} || { echo "ERROR: Tracking branch failed"; exit 1; }
          else
            echo "ERROR: Branch ${branchName} does not exist"
            exit 1
          fi

          ${
            if cfg.source.updateOnBoot then
              ''
                git pull origin ${branchName} || { 
                  echo "WARNING: Failed to pull, trying reset"
                  git reset --hard origin/${branchName} || { echo "ERROR: Update failed"; exit 1; }
                }
                ensure_clean_latest_checkout || { echo "ERROR: Could not sync to latest origin/${branchName}."; exit 1; }
              ''
            else
              ""
          }
        fi

        # --- DB SETUP ---
        cd ${repoDir}
        direnv allow

        mkdir -p ${envConfDir} ${envDataDir}


        # --- ENV SETUP ---
        echo "Running Django application configuration setup..."
        cd ${repoDir}

        source ${lxAnnotateEnvHelpers}
        lx_annotate_export_base_env
        lx_annotate_export_storage_env "${envDataDir}"
        lx_annotate_export_django_paths_env
        lx_annotate_export_db_env
        export DJANGO_DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD"
        lx_annotate_export_secret_key_env
        lx_annotate_export_oidc_env
        export EXEMPT_URLS="^/accounts/login/$"
        export LOGIN_URL="/accounts/login/"

        # Deployment markers
        echo "${envDjangoEnv}" > .mode
        chmod 600 .mode 2>/dev/null || true

        if [ -f .env ]; then
          echo "Aligning .env with production settings module"
          export DESIRED_SETTINGS_MODULE="${envAnnotateDjangoSettingsModule}"
          export DESIRED_ENVIRONMENT="${envDjangoEnv}"
      
          python - <<'PY'
    import os
    from pathlib import Path

    env_path = Path('.env')
    desired_module = os.environ['DESIRED_SETTINGS_MODULE']
    desired_env = os.environ['DESIRED_ENVIRONMENT']

    if not env_path.exists():
        raise SystemExit(0)

    lines = env_path.read_text(encoding='utf-8').splitlines()
    updated = []
    have_module = False
    have_env = False

    for line in lines:
        if line.startswith('DJANGO_SETTINGS_MODULE='):
            updated.append(f'DJANGO_SETTINGS_MODULE={desired_module}')
            have_module = True
        elif line.startswith('DJANGO_ENV='):
            updated.append(f'DJANGO_ENV={desired_env}')
            have_env = True
        else:
            updated.append(line)

    if not have_module:
        updated.append(f'DJANGO_SETTINGS_MODULE={desired_module}')

    if not have_env:
        updated.append(f'DJANGO_ENV={desired_env}')

    env_path.write_text('\n'.join(updated) + '\n', encoding='utf-8')
PY
        else
          echo "WARNING: .env not found"
        fi

        # --- CONFIG DIRS ---
        CONFIG_DIR="${endoreg-service-user-home}/config"
        if [ ! -d "$CONFIG_DIR" ]; then
          mkdir -p "$CONFIG_DIR"
        fi

        SECRETSPEC_CONFIG_DIR="${endoreg-service-user-home}/lx-annotate/.config/secretspec"
        mkdir -p "$SECRETSPEC_CONFIG_DIR"

        echo "Generating secretspec configuration..."
        cat > "$SECRETSPEC_CONFIG_DIR/config.toml" <<EOF
    [defaults]
    provider = "env"
    profile = "production"
EOF



        cat > ${repoDir}/.env.systemd <<EOF
    HOME_DIR=${endoreg-service-user-home}
    DATA_DIR=${envDataDir}
    CONF_DIR=${envConfDir}
    CONF_TEMPLATE_DIR=${envConfTemplateDir}
    WORKING_DIR=${repoDir}
    DJANGO_STATIC_ROOT=${staticRootPath}
    STORAGE_DIR=${envDataDir}
    IO_DIR=${envDataDir}
    SERVE_WITH_NGINX=true
    NGINX_PROTECTED_MEDIA_URL=/protected_media/
    DEBUG=False
    DJANGO_DEBUG=False
    VITE_ENABLE_DEBUG=${envViteEnableDebug}

    # --- Network & Host Configuration ---
    HTTP_PROTOCOL=${envHttpProtocol}
    DJANGO_HOST=${envDjangoHost}
    DJANGO_PORT=${envDjangoPort}
    BASE_URL=${envBaseUrl}
    DJANGO_ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
    ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
    DJANGO_CSRF_TRUSTED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
EOF
    currentRevision="$(git rev-parse --verify HEAD 2>/dev/null || echo unknown)"
        bootstrapStampFile="${envConfDir}/.bootstrap-revision"
        lastBootstrapRevision="$(cat "$bootstrapStampFile" 2>/dev/null || true)"
        runHeavyBootstrap="false"
        runtimeViteManifestSourcePath="${staticRootPath}/manifest.json"
        preferredViteManifestSourcePath="${repoDir}/lx_annotate/static/.vite/manifest.json"
        fallbackViteManifestSourcePath="${repoDir}/static/.vite/manifest.json"
        viteManifestPath="${staticRootPath}/.vite/manifest.json"

        resolve_vite_manifest_source() {
          if [ -f "$runtimeViteManifestSourcePath" ]; then
            printf '%s\n' "$runtimeViteManifestSourcePath"
            return 0
          fi
          if [ -f "$preferredViteManifestSourcePath" ]; then
            printf '%s\n' "$preferredViteManifestSourcePath"
            return 0
          fi
          if [ -f "$fallbackViteManifestSourcePath" ]; then
            printf '%s\n' "$fallbackViteManifestSourcePath"
            return 0
          fi
          return 1
        }

        vite_main_entry_file() {
          local manifest_path="$1"
          ${pkgs.python3}/bin/python3 - "$manifest_path" <<'PY'
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
PY
        }

        vite_manifest_points_to_existing_asset() {
          local manifest_path="$1"
          local main_entry_file=""
          if [ ! -f "$manifest_path" ]; then
            return 1
          fi
          main_entry_file="$(vite_main_entry_file "$manifest_path" 2>/dev/null || true)"
          if [ -z "$main_entry_file" ]; then
            return 1
          fi
          [ -f "${staticRootPath}/$main_entry_file" ]
        }

        if [ ! -f "$bootstrapStampFile" ]; then
          echo "No bootstrap stamp found; running full bootstrap tasks."
          runHeavyBootstrap="true"
        elif [ "$currentRevision" != "$lastBootstrapRevision" ]; then
          echo "Revision changed ($lastBootstrapRevision -> $currentRevision); running full bootstrap tasks."
          runHeavyBootstrap="true"
        else
          echo "Revision unchanged ($currentRevision); using lightweight startup path."
        fi
        

        echo "Collecting static files..."
        export DJANGO_STATIC_ROOT="${staticRootPath}"
        if [ "''${DJANGO_STATIC_ROOT%/}" = "${viteSourcePath}" ]; then
          echo "ERROR: DJANGO_STATIC_ROOT points to Vite source assets (${viteSourcePath})."
          echo "Use ${staticRootPath} as STATIC_ROOT to keep collectstatic isolated from frontend build output."
          exit 1
        fi
        ${devenvSyncCompatExports}



        if [ -d ".devenv/profile/bin" ]; then
          export PATH="${repoDir}/.devenv/profile/bin:$PATH"
        fi

        if [ -f ".devenv/state/venv/bin/activate" ]; then
          source .devenv/state/venv/bin/activate
        elif [ -f ".venv/bin/activate" ]; then
          source .venv/bin/activate
        fi

        if [ -n "$LOCK_HASH" ] && command -v uv >/dev/null 2>&1; then
          previousLockHash="$(cat "$SYNC_STAMP" 2>/dev/null || true)"
          if [ ! -x ".devenv/state/venv/bin/python" ] || [ "$LOCK_HASH" != "$previousLockHash" ]; then
            echo "uv deps changed or venv missing -> syncing..."
            eval "$SYNC_CMD" || echo "WARNING: uv sync failed; continuing with existing environment."
            printf '%s\n' "$LOCK_HASH" > "$SYNC_STAMP"
          else
            echo "uv deps unchanged -> skipping sync."
          fi
        fi

        run_collectstatic() {
          python manage.py collectstatic "$@"
        }

        run_migrate() {
          python manage.py migrate --noinput
        }

        run_load_base_data() {
          python manage.py load_base_db_data
        }


        run_server() {
          if command -v devenv >/dev/null 2>&1; then
            exec devenv shell -- bash -c "run-server"
          else
            echo "ERROR: run-server command not found in current environment."
            return 1
          fi
        }

        if [ "$runHeavyBootstrap" = "true" ]; then
          echo "Skipping routine vue-build on startup; collecting static + migrations only."
          run_collectstatic --noinput --clear
        else
          echo "Skipping collectstatic on unchanged revision."
        fi

        echo "Running Database Migrations..."
        run_migrate
        if [ "$runHeavyBootstrap" = "true" ]; then
          run_load_base_data
          printf '%s\n' "$currentRevision" > "$bootstrapStampFile"
          chmod 600 "$bootstrapStampFile" 2>/dev/null || true
        else
          echo "Skipping base data load on unchanged revision."
        fi


        if ! vite_manifest_points_to_existing_asset "$viteManifestPath"; then
          echo "ERROR: Vite manifest is missing/invalid after startup preparation: $viteManifestPath"
          exit 1
        fi

        echo "Starting Django server..."
        run_server
  '';
  watcherScriptName = "runLocalFileWatcher";
  runLocalFileWatcherScript = pkgs.writeShellScriptBin "${watcherScriptName}" ''
    set -euo pipefail

    # 1. Go to the repo (Cloned by the main boot service)
    cd ${repoDir}

    # 2. Re-Export ALL necessary Environment Variables
    # (Note: We skip git clone/pull because the boot service handles that)

    source ${lxAnnotateEnvHelpers}
    lx_annotate_export_base_env
    lx_annotate_export_storage_env "${envDataDir}"
    lx_annotate_export_db_env
    lx_annotate_export_secret_key_env
    export DJANGO_STATIC_ROOT=${staticRootPath}
    ${devenvSyncCompatExports}

    # 4. Start the Watcher inside the devenv shell
    echo "📁 Starting File Watcher..."

    if [ -f Makefile ] && command -v devenv >/dev/null 2>&1; then
      exec ${makeBin} REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" start-watcher
    fi

    exec devenv shell run-filewatcher
  '';
  runLocalExportFramesScript = pkgs.writeShellScriptBin "${exportFramesScriptName}" ''
    set -euo pipefail

    # 1. Go to the repo (Cloned by the main boot service)
    cd ${repoDir}

    # 2. Re-Export ALL necessary Environment Variables
    source ${lxAnnotateEnvHelpers}
    exportFramesStorageRoot="${exportFramesStorageRootDefault}"
    if [ ! -d "$exportFramesStorageRoot" ] || [ ! -w "$exportFramesStorageRoot" ]; then
      exportFramesStorageRoot="${envDataDir}"
    fi

    lx_annotate_export_base_env
    lx_annotate_export_storage_env "$exportFramesStorageRoot"
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
      exec ${makeBin} REPO_DIR="${repoDir}" CACHE_DIR="${makeCacheDir}" start-export
    fi

    exec devenv shell -- bash -c "STORAGE_DIR='$exportFramesStorageRoot' IO_DIR='$exportFramesStorageRoot' DATA_DIR='$exportFramesStorageRoot' export-frames"
  '';

in
{
  options.services.luxnix.lxAnnotateLocal = {
    enable = mkBoolOpt false "Enable LxAnnotate Service";

    # Debug configuration
    debug = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Enable verbose debug output including sensitive file information. Should be disabled in production.";
          };
        };
      };
      default = { };
      description = "Debug configuration for lx-annotate-local.";
    };

    # Source/Repository configuration
    source = mkOption {
      type = types.submodule {
        options = {
          url = mkOption {
            type = types.str;
            default = "https://github.com/wg-lux/lx-annotate";
            description = "Git repository URL for the lx-annotate application.";
          };
          branch = mkOption {
            type = types.str;
            default = "erc";
            description = "Git branch to checkout for lx-annotate.";
          };
          updateOnBoot = mkOption {
            type = types.bool;
            default = true;
            description = "Whether to update the lx-annotate repository on service start.";
          };
        };
      };
      default = { };
      description = "Repository configuration for lx-annotate.";
    };

    # Django configuration (passed from endoreg-client role)
    django = mkOption {
      type = types.submodule {
        options = mkDjangoOptions {
          defaults = {
            hostname = "lx-annotate.local";
            port = 8117;
            useHttps = false;
            sslCertificatePath = null;
            sslKeyPath = null;
            djangoAllowedHosts = [
              "lx-annotate.local"
              "127.0.0.1"
            ];
            corsAllowedOrigins = [
              "https://lx-annotate.local"
              "http://127.0.0.1"
            ];
            djangoDebug = false;
            djangoSecretKeyFile = "/etc/secrets/vault/django_secret_key";
            keycloakSecretFile = "/etc/secrets/vault/keycloak.env";
            keycloakClientId = "endoregdb-api";
            logLevel = "INFO";
            maxRequestSize = "100M";
            timeZone = "Europe/Berlin";
            language = "en-us";
            settingsProfile = "prod";
            settingsModule = null;
            djangoEnv = null;
            dataDir = "data";
            confDir = "conf";
            confTemplateDir = "conf_template";
            djangoModule = "lx_annotate";
            assetDir = "tests/assets";
            httpProtocol = "http";
            baseUrl = null;
            staticUrl = "/static/";
            mediaUrl = "/media/";
            runVideoTests = false;
            skipExpensiveTests = true;
            extraSettings = { };
          };
          includeKeycloak = true;
          logLevelType = types.str;
          httpProtocolType = types.str;
        };
      };
      default = { };
      description = "Django configuration options for lx-annotate.";
    };

    # Database configuration
    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption {
            type = types.str;
            default = "lx-annotate.local";
          };
          port = mkOption {
            type = types.port;
            default = 5433;
          };
          name = mkOption {
            type = types.str;
            default = "lxAnnotateLocal";
          };
          user = mkOption {
            type = types.str;
            default = "lxAnnotateLocal";
          };
          passwordFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
          };
          sslMode = mkOption {
            type = types.str;
            default = "prefer";
          };
          endoregLocalUserPasswordFile = mkOption {
            type = types.path;
            default = "/var/lib/postgresql/endoregDbLocal.password";
            description = "Path to file containing endoregDbLocal user password";
          };
        };
      };
      default = { };
      description = "Database configuration options";
    };
  };

  config = mkIf cfg.enable {
    services.luxnix.lxAnnotateLocal.django.djangoAllowedHosts = mkAfter [
      cfg.django.hostname
    ];
    services.luxnix.lxAnnotateLocal.django.sslCertificatePath = mkDefault defaultSslCertificatePath;
    services.luxnix.lxAnnotateLocal.django.sslKeyPath = mkDefault defaultSslKeyPath;
    services.luxnix.lxSsl.enable = mkDefault true;
    services.nginx = {
      enable = true;

      # This handles cases where certs were generated with 0600 root:root permissions.
      preStart = lib.mkAfter "${pkgs.writeShellScript "fix-ssl-perms-root" ''
        if [ -d "/var/lib/lx-annotate/ssl" ]; then
          echo "Fixing Nginx SSL permissions (running as root)..."
          ${pkgs.coreutils}/bin/chown -R root:nginx /var/lib/lx-annotate/ssl
          ${pkgs.coreutils}/bin/chmod 0750 /var/lib/lx-annotate/ssl
          ${pkgs.coreutils}/bin/chmod 0640 /var/lib/lx-annotate/ssl/* 2>/dev/null || true
        fi
      ''}";

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
        '';
        locations."/static/" = {
          # Must match STATIC_ROOT from Step 1
          alias = "${staticRootPath}/";
          extraConfig = "expires 30d; add_header Cache-Control 'public';";
        };

        locations."/media/" = {
          # Must match MEDIA_URL env var
          alias = "${envDataDir}/";
          extraConfig = "sendfile on; tcp_nopush on;";
        };

        locations."/protected_media/" = {
          alias = "${envDataDir}/";
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
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;
            proxy_buffering off;
          '';
        };
      };
    };

    luxnix.generic-settings.postgres = {
      enable = true;
    };

    # Ensure directory structure exists with correct permissions
    users.users.nginx.extraGroups = [ "${endoreg-service-group-name}" ];

    systemd.tmpfiles.rules = [
      "d ${endoreg-service-user-home} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      # Important for make-based bootstrap:
      # do not pre-create ${repoDir} or repo-internal paths here. The seed clone
      # expects the checkout target to be absent (or at least empty), and creating
      # ${envDataDir}/${staticRootPath} makes it non-empty before git runs.

      # 1. The Parent Directory: Create (d) AND Enforce (z) permissions
      "d /var/lib/lx-annotate 0750 root nginx - -"
      "z /var/lib/lx-annotate 0750 root nginx - -"

      # 2. The SSL Directory: Create (d) AND Enforce (z) permissions
      "d /var/lib/lx-annotate/ssl 0750 root nginx - -"
      "z /var/lib/lx-annotate/ssl 0750 root nginx - -"

      # File mode normalization is handled by nginx preStart to avoid
      # recursive 0640 on directories.
    ]
    ++ lib.optionals (!config.roles.endoreg-client.enable) [
      # Create the config subdirectory (handled by endoreg-client role when enabled)
      "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
    ];

    systemd.services."lx-annotate-boot" = {
      description = "Clone or pull lx-annotate and run prod-server";
      wantedBy = [ "multi-user.target" ];
      wants = [
        "nginx.service"
        "postgres-endoreg-setup.service"
      ];
      after = [
        "postgres-endoreg-setup.service"
        "endoreg-django-setup.service"
        "systemd-tmpfiles-setup.service"
      ];
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        WorkingDirectory = endoreg-service-user-home;
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
        TimeoutStartSec = "10s";
        ExecStartPre = "+${pkgs.writeShellScript "lx-annotate-pre-start" ''
          set -euo pipefail

          # 1. Fix Repo Permissions
          if [ -e ${repoDir} ]; then
            ${pkgs.coreutils}/bin/chown -R ${endoreg-service-user-name}:${endoreg-service-group-name} ${repoDir}
          fi

          # 2. Handle the Password File securely
          mkdir -p ${envConfDir}

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

          # Ensure the service user owns the directory too
          chown -R ${endoreg-service-user-name}:${endoreg-service-group-name} ${envConfDir}
        ''}";
        ExecStart = "${runLocalLxAnnotateScript}/bin/${scriptName}";
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
          "/var/lib/lx-annotate"
        ];
        # Resource limits
        MemoryHigh = "4G";
        MemoryMax = "6G";
        CPUQuota = "50%";
        Nice = 10;
        
        # 2. Disk I/O: leave headroom for the rest of the system during startup
        IOSchedulingClass = "best-effort";
        IOSchedulingPriority = 6;

        # 3. Memory Protection
        # Prefer killing/restarting this service over killing core host processes.
        OOMScoreAdjust = 250;
      };
    };
    systemd.services.lx-annotate-filewatcher = {
      description = "Django File Watcher Service";
      wantedBy = [ "multi-user.target" ];
      after = [ "postgresql.service" ]; # Adjust based on your DB
      requires = [ "lx-annotate-boot.service" ];

      serviceConfig = {
        User = endoreg-service-user-name; # Or whatever user runs the app
        WorkingDirectory = repoDir;
        ExecStart = "${runLocalFileWatcherScript}/bin/${watcherScriptName}";
        Restart = "always";
        RestartSec = "10m";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
        MemoryHigh = "1G";
        MemoryMax = "2G";
        CPUQuota = "35%";

        # 1. CPU Priority: Lower priority (Higher "Nice" value = nicer to others)
        Nice = 19; 

        # 2. Disk I/O Class: "idle"
        # This process will only get disk time when no other process needs it.
        # This solves the streaming stutter immediately.
        IOSchedulingClass = "idle";
        
        # 3. OOM Score: If RAM runs out, kill this service first, never the web server.
        OOMScoreAdjust = 1000;
      };
    };

    systemd.services.lx-annotate-export-frames = {
      description = "Export annotated frames for lx-annotate";
      after = [ "lx-annotate-boot.service" ];
      requires = [ "lx-annotate-boot.service" ];

      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        WorkingDirectory = repoDir;
        ExecStart = "${runLocalExportFramesScript}/bin/${exportFramesScriptName}";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
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
