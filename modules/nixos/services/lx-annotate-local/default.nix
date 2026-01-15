{ config
, lib
, pkgs
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.lxAnnotateLocal;
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;

  adminName = config.user.admin.name;
  scriptName = "runLocalLxAnnotate";

  # Use configuration options from new structure
  gitURL = cfg.source.url;
  repoDirName = "lx-annotate";
  branchName = cfg.source.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";
  staticRootPath = "${repoDir}/staticfiles";

  # Environment variable configuration from django submodule
  envDataDir = "${repoDir}/${cfg.django.dataDir}";
  envConfDir = "${repoDir}/${cfg.django.confDir}";
  envConfTemplateDir = "${repoDir}/${cfg.django.confTemplateDir}";
  envDjangoModule = cfg.django.djangoModule;
  envHttpProtocol = if cfg.django.httpProtocol != "http" then cfg.django.httpProtocol else (if cfg.django.useHttps then "https" else "http");
  envDjangoHost = cfg.django.hostname;
  envDjangoPort = toString cfg.django.port;
  envBaseUrl = 
    if cfg.django.baseUrl != null 
    then cfg.django.baseUrl 
    else "${envHttpProtocol}://${envDjangoHost}:${envDjangoPort}";

  makeAbsolute = path: if lib.hasPrefix "/" path then path else "${repoDir}/${path}";

  envStorageDir = makeAbsolute cfg.django.storageDir;
  envAssetDir = makeAbsolute cfg.django.assetDir;
  envStaticUrl = cfg.django.staticUrl;
  envMediaUrl = cfg.django.mediaUrl;
  envRunVideoTests = if cfg.django.runVideoTests then "true" else "false";
  envSkipExpensiveTests = if cfg.django.skipExpensiveTests then "true" else "false";

  settingsProfile = cfg.django.settingsProfile;
  envIsCentralNode = cfg.django.extraSettings.IS_CENTRAL_NODE or false;
  envDjangoSettingsModule = "lx_annotate.settings.settings_prod";
  envDjangoEnv = "production";
  envCentralNodeFlag = if envIsCentralNode || settingsProfile == "central" then "true" else "false";
  
  # Default center from django extraSettings
  envDefaultCenter = cfg.django.extraSettings.DEFAULT_CENTER or "university_hospital_wuerzburg";

  runLocalLxAnnotateScript = pkgs.writeShellScriptBin "${scriptName}" ''
    set -euo pipefail
    
    # Debug mode flag - controls verbose logging
    DEBUG_MODE=${if cfg.debug.enable then "true" else "false"}

    echo "Starting LxAnnotate service..."
    echo "Repository: ${gitURL}"
    echo "Branch: ${branchName}"
    echo "Target Directory: ${repoDir}"
    
    # Clone or update repository
    if [ ! -d ${repoDir} ]; then
      echo "Cloning repository..."
      git clone ${gitURL} ${repoDir}
      cd ${repoDir}
      direnv allow
    else
      cd ${repoDir}
      ${if cfg.source.updateOnBoot then ''
        echo "Updating repository..."
        git fetch origin || { echo "ERROR: Failed to fetch from origin"; exit 1; }
      '' else ''
        echo "Repository update disabled, using existing code"
      ''}
    fi
    
    # Checkout specified branch with proper remote tracking
    echo "Checking out branch: ${branchName}"
    if git show-ref --verify --quiet refs/heads/${branchName}; then
      # Local branch exists, switch to it
      echo "Local branch ${branchName} exists, switching to it"
      git checkout ${branchName} || { echo "ERROR: Failed to checkout local branch ${branchName}"; exit 1; }
    elif git show-ref --verify --quiet refs/remotes/origin/${branchName}; then
      # Remote branch exists, create local tracking branch
      echo "Remote branch origin/${branchName} exists, creating local tracking branch"
      git checkout -b ${branchName} origin/${branchName} || { echo "ERROR: Failed to create tracking branch for ${branchName}"; exit 1; }
    else
      echo "ERROR: Branch ${branchName} does not exist locally or on remote"
      echo "Available remote branches:"
      git branch -r || echo "Could not list remote branches"
      exit 1
    fi
    
    ${if cfg.source.updateOnBoot then ''
    # Update the current branch
    echo "Updating branch ${branchName}..."
    git pull origin ${branchName} || { 
      echo "WARNING: Failed to pull latest changes for ${branchName}, trying to reset to remote"
      git reset --hard origin/${branchName} || { 
        echo "ERROR: Failed to update branch ${branchName}"
        exit 1
      }
    }
    '' else ""}

    #################### DB SETUP ####################
    # Copy database password from vault (managed by postgres-default role)
    echo "Setting up database configuration..."
    
    if [ "$DEBUG_MODE" = "true" ]; then
      echo "Current user: $(whoami)"
      echo "User groups: $(groups)"
      echo "Checking for database password file: ${cfg.database.passwordFile}"
    fi

    cd ${repoDir}
    direnv allow
    echo "Collecting static files..."
    export DJANGO_STATIC_ROOT="${staticRootPath}"
    mkdir -p "$DJANGO_STATIC_ROOT"
    
    # Run collectstatic via devenv or python directly
    if command -v devenv >/dev/null 2>&1; then
       devenv shell -- python manage.py collectstatic --noinput --clear
    else
       source .venv/bin/activate 
       python manage.py collectstatic --noinput --clear
    fi

    
    # Ensure runtime directories exist (they might be ignored in git)
    mkdir -p ${envConfDir} ${envDataDir} ${envStorageDir}
    
    if [ -f "$SECRET_FILE" ] && head -c 1 "$SECRET_FILE" >/dev/null 2>&1; then
      cp "$SECRET_FILE" ${envConfDir}/db_pwd
      echo "Database password copied from vault to ${envConfDir}/db_pwd"
      
      # Run Django application's configuration setup
      echo "Running Django application configuration setup..."
      cd ${repoDir}
      
      # Set environment variables needed by the Django config scripts
      export DATA_DIR="${envDataDir}"
      export STORAGE_DIR="${envStorageDir}"
      export CONF_DIR="${envConfDir}"
      export CONF_TEMPLATE_DIR="${envConfTemplateDir}"
      export WORKING_DIR="${repoDir}"
      export HOME_DIR="${endoreg-service-user-home}"
      export DB_PWD_FILE="${envConfDir}/db_pwd"
      export DJANGO_MODULE="${envDjangoModule}"
      export DJANGO_SETTINGS_MODULE="${envDjangoSettingsModule}"
      export DJANGO_SETTINGS_MODULE_PRODUCTION="settings.settings_prod"
      export DJANGO_SETTINGS_MODULE_DEVELOPMENT="settings.settings_dev"
      export DJANGO_SETTINGS_MODULE_CENTRAL="settings.settings_central"
      export DJANGO_ENV="${envDjangoEnv}"
      export CENTRAL_NODE="${envCentralNodeFlag}"
      export HTTP_PROTOCOL="${envHttpProtocol}"
      export DJANGO_HOST="${envDjangoHost}"
      export DJANGO_PORT="${envDjangoPort}"
      export BASE_URL="${envBaseUrl}"
      export TIME_ZONE="${cfg.django.timeZone}"
      export STATIC_URL="${envStaticUrl}"
      export MEDIA_URL="${envMediaUrl}"
      export ASSET_DIR="${envAssetDir}"
      export RUN_VIDEO_TESTS="${envRunVideoTests}"
      export SKIP_EXPENSIVE_TESTS="${envSkipExpensiveTests}"


      DB_PASSWORD_VALUE="$(tr -d '\n' < ${envConfDir}/db_pwd 2>/dev/null || true)"
      export DB_ENGINE="django.db.backends.postgresql"
      export DB_NAME="${cfg.database.name}"
      export DB_USER="${cfg.database.user}"
      export DB_PASSWORD="$DB_PASSWORD_VALUE"
      export DB_HOST="${cfg.database.host}"
      export DB_PORT="${toString cfg.database.port}"
      export DB_SSLMODE="${cfg.database.sslMode}"
      # We wrap the JSON in single quotes '...' to ensure shell handles special chars correctly
      export DJANGO_ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
      export DJANGO_CORS_ALLOWED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
      export DJANGO_CSRF_TRUSTED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
      DJANGO_SECRET_KEY_VALUE="$(tr -d '\n' < ${cfg.django.djangoSecretKeyFile} 2>/dev/null || true)"
      export DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY_VALUE"

      # --- KEYCLOAK EXPORTS ---
      # 1. Export the Client ID (Value)
      export OIDC_RP_CLIENT_ID="${cfg.django.keycloakClientId}"
      
      # 2. Export the Secret File Path (Django will read the content)
      export OIDC_RP_CLIENT_SECRET="${cfg.django.keycloakSecretFile}"     
      # ------------------------

      
      # Ensure devenv is available and run the configuration script
      if command -v devenv >/dev/null 2>&1; then
        echo "Running Django configuration setup via devenv..."
        devenv shell env-init-conf || { 
          echo "WARNING: devenv env-init-conf failed, trying direct script execution"
          # Fallback to direct execution if devenv fails
          if [ -f "scripts/make_conf.py" ]; then
            python scripts/make_conf.py || echo "WARNING: make_conf.py execution failed"
          fi
        }

        echo "Building .env from template..."
        if ! devenv shell env-build; then
          echo "WARNING: devenv env-build failed, attempting direct execution"
          if ! devenv shell -- uv run env_setup.py; then
            if [ -f "env_setup.py" ]; then
              python env_setup.py || echo "WARNING: env_setup.py execution failed"
            fi
          fi
        fi
      else
        echo "devenv not available, trying direct script execution..."
        if [ -f "scripts/make_conf.py" ]; then
          python scripts/make_conf.py || echo "WARNING: make_conf.py execution failed"
        else
          echo "WARNING: scripts/make_conf.py not found"
        fi

        if [ -f "env_setup.py" ]; then
          echo "Building .env from template via python env_setup.py"
          python env_setup.py || echo "WARNING: env_setup.py execution failed"
        fi
      fi
      
      # Verify that the required db.yaml file was created
      if [ -f "${envConfDir}/db.yaml" ]; then
        echo "✓ Django configuration file created: ${envConfDir}/db.yaml"
      else
        echo "WARNING: Django configuration file ${envConfDir}/db.yaml was not created"
        echo "Contents of conf directory:"
        ls -la "${envConfDir}/" 2>/dev/null || echo "Cannot access conf directory"
      fi

      # Force production mode indicators for the devenv shell helpers
      echo "Setting deployment mode markers..."
      echo "${envDjangoEnv}" > .mode
      chmod 600 .mode 2>/dev/null || true

      if [ -f .env ]; then
        echo "Aligning .env with production settings module"
        export DESIRED_SETTINGS_MODULE="${envDjangoSettingsModule}"
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
        echo "WARNING: .env not found after setup; production overrides skipped"
      fi
      
    else
      echo "ERROR: Database password not found in vault or not accessible. PostgreSQL setup may not be complete."
      exit 1
    fi

    # Copy Django configuration
    echo "Setting up Django configuration..."
    echo "Service user home: ${endoreg-service-user-home}"
    echo "Current user: $(whoami)"
    echo "Current directory: $(pwd)"
    
    # Check if home directory exists and is accessible
    if [ ! -d "${endoreg-service-user-home}" ]; then
      echo "ERROR: Home directory ${endoreg-service-user-home} does not exist"
      exit 1
    fi
    
    # Ensure config directory exists with correct permissions
    CONFIG_DIR="${endoreg-service-user-home}/config"
    echo "Checking config directory: $CONFIG_DIR"
    
    if [ ! -d "$CONFIG_DIR" ]; then
      echo "Creating config directory: $CONFIG_DIR"
      mkdir -p "$CONFIG_DIR" || { echo "ERROR: Failed to create config directory $CONFIG_DIR"; ls -la "${endoreg-service-user-home}"; exit 1; }
    else
      echo "Config directory already exists"
    fi
    
    # Check permissions
    ls -la "${endoreg-service-user-home}/" || echo "Cannot list home directory contents"

    echo "Starting Django server..."
    echo "Hostname: ${envDjangoHost}"
    echo "Port: ${envDjangoPort}"
    echo "Protocol: ${envHttpProtocol}"
    
    # Write essential environment variables to .env.systemd for devenv
    cat > ${repoDir}/.env.systemd <<EOF
HOME_DIR=${endoreg-service-user-home}
DATA_DIR=${envDataDir}
STORAGE_DIR=${envStorageDir}
CONF_DIR=${envConfDir}
CONF_TEMPLATE_DIR=${envConfTemplateDir}
WORKING_DIR=${repoDir}
DJANGO_STATIC_ROOT=${staticRootPath}
EOF

    # Start the Django application with devenv
    exec devenv shell -- run-server
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
      default = {};
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
            default = "main";
            description = "Git branch to checkout for lx-annotate.";
          };
          updateOnBoot = mkOption {
            type = types.bool;
            default = true;
            description = "Whether to update the lx-annotate repository on service start.";
          };
        };
      };
      default = {};
      description = "Repository configuration for lx-annotate.";
    };

    # Django configuration (passed from endoreg-client role)
    django = mkOption {
      type = types.submodule {
        options = {
          hostname = mkOption { type = types.str; default = "lx-annotate.net"; };
          port = mkOption { type = types.port; default = 8118; };
          useHttps = mkOption { type = types.bool; default = false; };
          sslCertificatePath = mkOption { type = types.nullOr types.path; default = null; };
          sslKeyPath = mkOption { type = types.nullOr types.path; default = null; };
          djangoAllowedHosts = mkOption { type = types.listOf types.str; default = ["lx-annotate.net" "127.0.0.1"]; };
          djangoDebug = mkOption { type = types.bool; default = false; };
          djangoSecretKeyFile = mkOption { type = types.path; default = "/etc/secrets/vault/django_secret_key"; };
          
          keycloakSecretFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/keycloak.env";
            description = "Path to file containing the Keycloak Client Secret.";
          };

          keycloakClientId = mkOption {
            type = types.str;
            default = "EndoregDb-realm";
            description = "Keycloak Client ID.";
          };
          # -------------------------------

          corsAllowedOrigins = mkOption { type = types.listOf types.str; default = []; };
          logLevel = mkOption { type = types.str; default = "INFO"; };
          maxRequestSize = mkOption { type = types.str; default = "100M"; };
          timeZone = mkOption { type = types.str; default = "Europe/Berlin"; };
          language = mkOption { type = types.str; default = "en-us"; };

          settingsProfile = mkOption {
            type = types.enum [ "dev" "prod" "central" "test" ];
            default = "prod";
            description = "Base settings profile to use when selecting Django settings modules.";
          };
          settingsModule = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Explicit Django settings module (overrides settingsProfile).";
          };
          djangoEnv = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Value for DJANGO_ENV; inferred from settingsProfile when null.";
          };
          
          # Environment variable configuration options
          dataDir = mkOption { 
            type = types.str; 
            default = "data"; 
            description = "Relative path to data directory within the repository";
          };
          storageDir = mkOption {
            type = types.str;
            default = "storage";
            description = "Relative or absolute path used for STORAGE_DIR.";
          };
          confDir = mkOption { 
            type = types.str; 
            default = "conf"; 
            description = "Relative path to configuration directory within the repository";
          };
          confTemplateDir = mkOption { 
            type = types.str; 
            default = "conf_template"; 
            description = "Relative path to configuration template directory within the repository";
          };
          djangoModule = mkOption { 
            type = types.str; 
            default = "lx_annotate"; 
            description = "Django module name for the application";
          };
          assetDir = mkOption {
            type = types.str;
            default = "tests/assets";
            description = "Relative or absolute path used as ASSET_DIR.";
          };
          httpProtocol = mkOption { 
            type = types.str; 
            default = "http"; 
            description = "HTTP protocol to use (http or https)";
          };
          baseUrl = mkOption { 
            type = types.nullOr types.str; 
            default = null; 
            description = "Base URL for the application. If null, will be constructed from protocol, host, and port";
          };
          staticUrl = mkOption {
            type = types.str;
            default = "/static/";
            description = "STATIC_URL value exported to the application.";
          };
          mediaUrl = mkOption {
            type = types.str;
            default = "/media/";
            description = "MEDIA_URL value exported to the application.";
          };
          runVideoTests = mkOption {
            type = types.bool;
            default = false;
            description = "Whether RUN_VIDEO_TESTS should be enabled.";
          };
          skipExpensiveTests = mkOption {
            type = types.bool;
            default = true;
            description = "Whether SKIP_EXPENSIVE_TESTS should be enabled.";
          };
          
          extraSettings = mkOption { 
            type = types.attrsOf types.anything; 
            default = {}; 
            description = "Additional settings to pass to Django configuration";
          };
        };
      };
      default = {};
      description = "Django configuration options for lx-annotate.";
    };

    # Database configuration
    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption { type = types.str; default = "lx-annotate.net"; };
          port = mkOption { type = types.port; default = 5433; };
          name = mkOption { type = types.str; default = "lxAnnotateLocal"; };
          user = mkOption { type = types.str; default = "lxAnnotateLocal"; };
          passwordFile = mkOption { type = types.path; default = "/etc/secrets/vault/SCRT_local_password_maintenance_password"; };
          sslMode = mkOption { type = types.str; default = "prefer"; };
        };
      };
      default = {};
      description = "Database configuration options";
    };
  };

  config = mkIf cfg.enable {
    services.luxnix.lxAnnotateLocal.django.djangoAllowedHosts = mkAfter [
      cfg.django.hostname
    ];

    services.nginx = {
      enable = true;
      
      # Tuning for AI Model Uploads (50GB) & Streaming
      recommendedProxySettings = true;
      recommendedTlsSettings = true;
      
      virtualHosts."${cfg.django.hostname}" = {
        listen = [ { addr = "0.0.0.0"; port = 80; } ]; # Or 443 with enableACME
        
        # 1. Allow massive uploads for AI Models
        extraConfig = ''
          client_max_body_size 50G;
          proxy_request_buffering off;
        '';

        locations."/static/" = {
          # Must match STATIC_ROOT from Step 1
          alias = "${staticRootPath}/";
          extraConfig = "expires 30d; add_header Cache-Control 'public';";
        };

        locations."/media/" = {
          # Must match MEDIA_ROOT env var
          alias = "${endoreg-service-user-home}/${repoDirName}/${cfg.django.dataDir}/";
          extraConfig = "sendfile on; tcp_nopush on;";
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
    users.users.nginx.extraGroups = [ "${endoreg-service-user-name}" ];

    systemd.tmpfiles.rules = [
      # Allow nginx to traverse the service user's home directory
      "d ${endoreg-service-user-home} 0751 ${endoreg-service-user-name} ${endoreg-service-user-name} - -"
      # Create the config subdirectory
      "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-user-name} - -"
      # Ensure static dir exists for nginx alias
      "d ${staticRootPath} 0755 ${endoreg-service-user-name} ${endoreg-service-user-name} - -"
    ];
    
    systemd.services."lx-annotate-boot" = {
      description = "Clone or pull lx-annotate and run prod-server";
      wantedBy = [ "multi-user.target" ];
      after = [ "postgres-endoreg-setup.service" "endoreg-django-setup.service" "systemd-tmpfiles-setup.service" ];
      requires = [ "postgres-endoreg-setup.service" "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        Environment = [
        "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:/run/current-system/sw/bin"
        "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
        ExecStart = "${runLocalLxAnnotateScript}/bin/${scriptName}";
        Restart = "on-failure";
        RestartSec = "10s";
        # Resource limits
        MemoryMax = "8G";
        CPUQuota = "800%";
      };
    };
  };
}