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

  # Use configuration options or fallback to defaults
  sourceCfg = cfg.source;
  djangoCfg = cfg.django;
  runtimeCfg = cfg.runtime;
  serverCfg = runtimeCfg.server;
  envConfig = runtimeCfg.environment;
  limitsCfg = runtimeCfg.limits;
  debugCfg = cfg.debug;

  gitURL = sourceCfg.url;
  repoDirName = "lx-annotate";
  branchName = sourceCfg.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";

  # Environment variable configuration
  envDataDir = "${repoDir}/${djangoCfg.dataDir}";
  envConfDir = "${repoDir}/${djangoCfg.confDir}";
  envConfTemplateDir = "${repoDir}/${djangoCfg.confTemplateDir}";
  envDjangoModule = djangoCfg.djangoModule;
  envHttpProtocol = if djangoCfg.httpProtocol != "http" then djangoCfg.httpProtocol else (if djangoCfg.useHttps then "https" else "http");
  envDjangoHost = djangoCfg.hostname;
  envDjangoPort = toString djangoCfg.port;
  envBaseUrl = 
    if djangoCfg.baseUrl != null 
    then djangoCfg.baseUrl 
    else "${envHttpProtocol}://${envDjangoHost}:${envDjangoPort}";

  makeAbsolute = path: if lib.hasPrefix "/" path then path else "${repoDir}/${path}";

  envStorageDir = makeAbsolute djangoCfg.storageDir;
  envAssetDir = makeAbsolute djangoCfg.assetDir;
  envStaticUrl = djangoCfg.staticUrl;
  envMediaUrl = djangoCfg.mediaUrl;
  envRunVideoTests = if djangoCfg.runVideoTests then "true" else "false";
  envSkipExpensiveTests = if djangoCfg.skipExpensiveTests then "true" else "false";
  envHfTransferFlag = if envConfig.hfHubEnableTransfer then "1" else "0";

  settingsProfile = djangoCfg.settingsProfile;
  envIsCentralNode = djangoCfg.extraSettings.IS_CENTRAL_NODE or false;
  derivedSettingsModule =
    if settingsProfile == "dev" then "config.settings.dev"
    else if settingsProfile == "central" then "config.settings.central"
    else if settingsProfile == "test" then "config.settings.test"
    else "config.settings.prod";
  envDjangoSettingsModule =
    if djangoCfg.settingsModule != null then djangoCfg.settingsModule
    else if envIsCentralNode && settingsProfile != "dev" && settingsProfile != "test" then "config.settings.central"
    else derivedSettingsModule;
  envDjangoEnv =
    if djangoCfg.djangoEnv != null then djangoCfg.djangoEnv
    else if envIsCentralNode || settingsProfile == "central" then "central"
    else if settingsProfile == "dev" then "development"
    else if settingsProfile == "test" then "test"
    else "production";
  envCentralNodeFlag = if envIsCentralNode || settingsProfile == "central" then "true" else "false";

  runLocalLxAnnotateScript = pkgs.writeShellScriptBin "${scriptName}" ''
    set -euo pipefail
    
    # Debug mode flag - controls verbose logging
  DEBUG_MODE=${if debugCfg.enable then "true" else "false"}

    echo "Starting LxAnnotate service..."
    echo "Repository: ${gitURL}"
    echo "Branch: ${branchName}"
    echo "Target Directory: ${repoDir}"
    
    # Clone or update repository
    if [ ! -d "${repoDir}" ]; then
      echo "Cloning repository..."
      git clone "${gitURL}" "${repoDir}"
      cd "${repoDir}"
    else
      cd "${repoDir}"
  ${if sourceCfg.updateOnBoot then ''
        echo "Updating repository..."
        git fetch origin || { echo "ERROR: Failed to fetch from origin"; exit 1; }
      '' else ''
        echo "Repository update disabled, using existing code"
      ''}
    fi
    
    # Checkout specified branch with proper remote tracking
    echo "Checking out branch: ${branchName}"
    if git show-ref --verify --quiet "refs/heads/${branchName}"; then
      # Local branch exists, switch to it
      echo "Local branch ${branchName} exists, switching to it"
      git checkout "${branchName}" || { echo "ERROR: Failed to checkout local branch ${branchName}"; exit 1; }
    elif git show-ref --verify --quiet "refs/remotes/origin/${branchName}"; then
      # Remote branch exists, create local tracking branch
      echo "Remote branch origin/${branchName} exists, creating local tracking branch"
      git checkout -b "${branchName}" "origin/${branchName}" || { echo "ERROR: Failed to create tracking branch for ${branchName}"; exit 1; }
    else
      echo "ERROR: Branch ${branchName} does not exist locally or on remote"
      echo "Available remote branches:"
      git branch -r || echo "Could not list remote branches"
      exit 1
    fi
    
  ${if sourceCfg.updateOnBoot then ''
    # Update the current branch
    echo "Updating branch ${branchName}..."
    git pull origin "${branchName}" || { 
      echo "WARNING: Failed to pull latest changes for ${branchName}, trying to reset to remote"
      git reset --hard "origin/${branchName}" || { 
        echo "ERROR: Failed to update branch ${branchName}"
        exit 1
      }
    }
    '' else ""}

    # Copy database password from vault (managed by postgres-default role)
    echo "Setting up database configuration..."
    
    if [ "$DEBUG_MODE" = "true" ]; then
      echo "Current user: $(whoami)"
      echo "User groups: $(groups)"
      echo "Checking for database password file: ${cfg.database.passwordFile}"
    fi
    
    # Debug secret file access
    SECRET_FILE="${cfg.database.passwordFile}"
    if [ -f "$SECRET_FILE" ]; then
      if [ "$DEBUG_MODE" = "true" ]; then
        echo "Secret file exists: $SECRET_FILE"
        ls -la "$SECRET_FILE" || echo "Cannot stat secret file"
        echo "Testing read access..."
      fi
      if head -c 10 "$SECRET_FILE" >/dev/null 2>&1; then
        if [ "$DEBUG_MODE" = "true" ]; then
          echo "✓ Can read secret file"
        fi
      else
        echo "✗ Cannot read secret file"
        if [ "$DEBUG_MODE" = "true" ]; then
          echo "File permissions:"
          ls -la "$SECRET_FILE" 2>/dev/null || echo "Cannot access file"
          echo "Directory permissions:"
          ls -la "$(dirname "$SECRET_FILE")" 2>/dev/null || echo "Cannot access directory" 
          echo "Parent directory permissions:"
          ls -la "/etc/secrets" 2>/dev/null || echo "Cannot access /etc/secrets"
        fi
      fi
    else
      echo "Secret file does not exist: $SECRET_FILE"
      if [ "$DEBUG_MODE" = "true" ]; then
        echo "Directory contents:"
        ls -la "$(dirname "$SECRET_FILE")" 2>/dev/null || echo "Cannot access $(dirname "$SECRET_FILE")"
        ls -la "/etc/secrets" 2>/dev/null || echo "Cannot access /etc/secrets"
      fi
    fi
    
  # Ensure runtime directories exist (they might be ignored in git)
  mkdir -p "${envConfDir}" "${envDataDir}" "${envStorageDir}"
    
  if [ -f "$SECRET_FILE" ] && head -c 1 "$SECRET_FILE" >/dev/null 2>&1; then
    cp "$SECRET_FILE" "${envConfDir}/db_pwd"
    echo "Database password copied from vault to ${envConfDir}/db_pwd"
  fi
  # Run Django application's configuration setup
  echo "Running Django application configuration setup..."
  cd "${repoDir}"
  
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
  export DJANGO_SETTINGS_MODULE_PRODUCTION="config.settings.prod"
  export DJANGO_SETTINGS_MODULE_DEVELOPMENT="config.settings.dev"
  export DJANGO_SETTINGS_MODULE_CENTRAL="config.settings.central"
  export DJANGO_ENV="${envDjangoEnv}"
  export CENTRAL_NODE="${envCentralNodeFlag}"
  export HTTP_PROTOCOL="${envHttpProtocol}"
  export DJANGO_HOST="${envDjangoHost}"
  export DJANGO_PORT="${envDjangoPort}"
  export BASE_URL="${envBaseUrl}"
  export TIME_ZONE="${djangoCfg.timeZone}"
  export STATIC_URL="${envStaticUrl}"
  export MEDIA_URL="${envMediaUrl}"
  export ASSET_DIR="${envAssetDir}"
  export RUN_VIDEO_TESTS="${envRunVideoTests}"
  export SKIP_EXPENSIVE_TESTS="${envSkipExpensiveTests}"

  DB_PASSWORD_VALUE="$(tr -d '\n' < "${envConfDir}/db_pwd" 2>/dev/null || true)"
  export DB_ENGINE="django.db.backends.postgresql"
  export DB_NAME="${cfg.database.name}"
  export DB_USER="${cfg.database.user}"
  export DB_PASSWORD="$DB_PASSWORD_VALUE"
  export DB_HOST="${cfg.database.host}"
  export DB_PORT="${toString cfg.database.port}"
  export DB_SSLMODE="${cfg.database.sslMode}"

  export HF_HOME=${lib.escapeShellArg envConfig.hfHome}
  export HF_HUB_CACHE=${lib.escapeShellArg envConfig.hfHubCache}
  export HF_HUB_ENABLE_HF_TRANSFER=${lib.escapeShellArg envHfTransferFlag}
  export OLLAMA_KEEP_ALIVE=${lib.escapeShellArg envConfig.ollamaKeepAlive}
  export OLLAMA_MODELS=${lib.escapeShellArg envConfig.ollamaModelsDir}
  export TRANSFORMERS_CACHE=${lib.escapeShellArg envConfig.transformersCache}

  echo "Ensuring Django environment templates are rendered..."
  if ! uv run python scripts/database/make_conf.py; then
    echo "❌ Database configuration failed"
    exit 1
  fi

  if ! uv run python scripts/core/setup.py; then
    echo "❌ Environment setup failed"
    exit 1
  fi

  if [ ! -f ".env" ]; then
    echo "WARNING: .env file missing after setup"
  else
    required_env_vars=(
      DJANGO_SETTINGS_MODULE DJANGO_ENV BASE_URL HTTP_PROTOCOL DJANGO_HOST DJANGO_PORT
      DB_ENGINE DB_NAME DB_USER DB_HOST DB_PORT DB_SSLMODE STATIC_URL MEDIA_URL
    )
    for var in "${required_env_vars[@]}"; do
      if ! grep -Eq "^${var}=" .env; then
        echo "WARNING: ${var} missing from .env; verify setup scripts populate it"
      fi
    done
  fi
   
    echo "Starting Django server..."
    echo "Hostname: ${envDjangoHost}"
    echo "Port: ${envDjangoPort}"
    echo "Protocol: ${envHttpProtocol}"
    
    # Start the Django application
    exec devenv shell -- run-server
  '';

in
{
  imports = [
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "api" ] [ "services" "luxnix" "lxAnnotateLocal" "django" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "repository" ] [ "services" "luxnix" "lxAnnotateLocal" "source" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "environment" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "environment" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "workers" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "server" "workers" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "maxRequests" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "server" "maxRequests" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "timeout" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "server" "timeout" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "keepAlive" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "server" "keepAlive" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "extraEnvironment" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "server" "extraEnvironment" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "memoryMax" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "limits" "memoryMax" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "service" "cpuQuota" ] [ "services" "luxnix" "lxAnnotateLocal" "runtime" "limits" "cpuQuota" ])
    (lib.mkRenamedOptionModule [ "services" "luxnix" "lxAnnotateLocal" "debugMode" ] [ "services" "luxnix" "lxAnnotateLocal" "debug" "enable" ])
  ];

  options.services.luxnix.lxAnnotateLocal = {
    enable = mkBoolOpt false "Enable Lx-Annotate Service";

    debug = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Enable verbose debug output including sensitive file information. Should be disabled in production.";
      };
    };

    source = mkOption {
      type = types.submodule {
        options = {
          url = mkOption { type = types.str; default = "https://github.com/wg-lux/lx-annotate"; };
          branch = mkOption { type = types.str; default = "erc"; };
          updateOnBoot = mkOption { type = types.bool; default = true; };
        };
      };
      default = {};
      description = "Repository configuration options";
    };

    django = mkOption {
      type = types.submodule {
        options = {
          hostname = mkOption { type = types.str; default = "localhost"; };
          port = mkOption { type = types.port; default = 8118; };
          useHttps = mkOption { type = types.bool; default = false; };
          sslCertificatePath = mkOption { type = types.nullOr types.path; default = null; };
          sslKeyPath = mkOption { type = types.nullOr types.path; default = null; };
          djangoAllowedHosts = mkOption { type = types.listOf types.str; default = ["localhost" "127.0.0.1"]; };
          djangoDebug = mkOption { type = types.bool; default = false; };
          djangoSecretKeyFile = mkOption { type = types.path; default = "/etc/secrets/vault/django_secret_key"; };
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

      type = types.str;
            default = "data";
            description = "Relative path to data directory within the repository.";
          };
          storageDir = mkOption {
            type = types.str;
            default = "storage";
            description = "Relative or absolute path used for STORAGE_DIR.";
          };
          confDir = mkOption {
            type = types.str;
            default = "conf";
            description = "Relative path to configuration directory within the repository.";
          };
          confTemplateDir = mkOption {
            type = types.str;
            default = "conf_template";
            description = "Relative path to configuration template directory within the repository.";
          };
          djangoModule = mkOption {
            type = types.str;
            default = "lx_annotate";
            description = "Django module name for the application.";
          };
          assetDir = mkOption {
            type = types.str;
            default = "tests/assets";
            description = "Relative or absolute path used as ASSET_DIR.";
          };
          httpProtocol = mkOption {
            type = types.str;
            default = "http";
            description = "HTTP protocol to use (http or https).";
          };
          baseUrl = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Base URL for the application. If null, will be constructed from protocol, host, and port.";
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
            description = "Additional settings to pass to Django configuration.";
          };
        };
      };
      default = {};
      description = "Django and HTTP configuration";
    };

    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption { type = types.str; default = "localhost"; };
          port = mkOption { type = types.port; default = 5432; };
          name = mkOption { type = types.str; default = "endoregDbLocal"; };
          user = mkOption { type = types.str; default = "endoregDbLocal"; };
          passwordFile = mkOption { type = types.path; default = "/etc/secrets/vault/SCRT_local_password_maintenance_password"; };
          sslMode = mkOption { type = types.str; default = "prefer"; };
        };
      };
      default = {};
      description = "Database configuration options";
    };

    runtime = mkOption {
      type = types.submodule {
        options = {
          server = mkOption {
            type = types.submodule {
              options = {
                workers = mkOption { type = types.int; default = 1; };
                maxRequests = mkOption { type = types.int; default = 1000; };
                timeout = mkOption { type = types.int; default = 30; };
                keepAlive = mkOption { type = types.int; default = 60; };
                extraEnvironment = mkOption { type = types.attrsOf types.str; default = {}; };
              };
            };
            default = {};
            description = "Application server runtime parameters.";
          };

          limits = mkOption {
            type = types.submodule {
              options = {
                memoryMax = mkOption {
                  type = types.str;
                  default = "8G";
                  description = "systemd MemoryMax limit applied to the lx-annotate service.";
                };
                cpuQuota = mkOption {
                  type = types.str;
                  default = "800%";
                  description = "systemd CPUQuota assigned to the lx-annotate service.";
                };
              };
            };
            default = {};
            description = "Systemd resource limits applied to the service.";
          };

          environment = mkOption {
            type = types.submodule {
              options = {
                hfHome = mkOption {
                  type = types.str;
                  default = "${endoreg-service-user-home}/.cache/huggingface";
                  description = "Location used for HF_HOME.";
                };
                hfHubCache = mkOption {
                  type = types.str;
                  default = "${endoreg-service-user-home}/.cache/huggingface/hub";
                  description = "Location used for HF_HUB_CACHE.";
                };
                hfHubEnableTransfer = mkOption {
                  type = types.bool;
                  default = true;
                  description = "Whether HF_HUB_ENABLE_HF_TRANSFER is set to 1.";
                };
                ollamaKeepAlive = mkOption {
                  type = types.str;
                  default = "4h";
                  description = "Value exported as OLLAMA_KEEP_ALIVE.";
                };
                ollamaModelsDir = mkOption {
                  type = types.str;
                  default = "${endoreg-service-user-home}/.ollama/models";
                  description = "Directory exported as OLLAMA_MODELS.";
                };
                transformersCache = mkOption {
                  type = types.str;
                  default = "${endoreg-service-user-home}/.cache/huggingface/hub";
                  description = "Location exported as TRANSFORMERS_CACHE.";
                };
              };
            };
            default = {};
            description = "Runtime environment variables applied when launching lx-annotate.";
          };
        };
      };
      default = {};
      description = "Runtime configuration for the lx-annotate application.";
    };
  # };
  
  config = mkIf cfg.enable {
    luxnix.generic-settings.postgres = {
      enable = true;
    };
    
    # Ensure directory structure exists with correct permissions
    systemd.tmpfiles.rules = [
      # Create the service user home directory
      "d ${endoreg-service-user-home} 0755 ${endoreg-service-user-name} ${endoreg-service-user-name} - -"
      # Create the config subdirectory  
      "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-user-name} - -"
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
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.uv}/bin:/run/current-system/sw/bin"
          "HOME_DIR=${endoreg-service-user-home}"
        ];
        ExecStart = "${runLocalLxAnnotateScript}/bin/${scriptName}";
        Restart = "on-failure";
        RestartSec = "10s";
        # Resource limits
        MemoryMax = limitsCfg.memoryMax;
        CPUQuota = limitsCfg.cpuQuota;
      };
    };
  };
}
