{ config
, lib
, pkgs
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.endoregDbApiLocal;
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;

  adminName = config.user.admin.name;
  scriptName = "runLocalEndoApi";

  # Use configuration options or fallback to defaults
  gitURL = cfg.repository.url;
  repoDirName = "endo-api";
  branchName = cfg.repository.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";

  # Environment variable configuration
  envDataDir = "${repoDir}/${cfg.api.dataDir}";
  envConfDir = "${repoDir}/${cfg.api.confDir}";
  envConfTemplateDir = "${repoDir}/${cfg.api.confTemplateDir}";
  envDjangoModule = cfg.api.djangoModule;
  envHttpProtocol = if cfg.api.httpProtocol != "http" then cfg.api.httpProtocol else (if cfg.api.useHttps then "https" else "http");
  envDjangoHost = cfg.api.hostname;
  envDjangoPort = toString cfg.api.port;
  envBaseUrl = 
    if cfg.api.baseUrl != null 
    then cfg.api.baseUrl 
    else "${envHttpProtocol}://${envDjangoHost}:${envDjangoPort}";

  # Django configuration file
  djangoConfigFile = pkgs.writeText "django-local-settings.py" ''
    # Auto-generated Django configuration for endoreg-api
    import os
    from pathlib import Path

    # Database Configuration
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': '${cfg.database.name}',
            'USER': '${cfg.database.user}',
            'PASSWORD': open('${cfg.database.passwordFile}').read().strip(),
            'HOST': '${cfg.database.host}',
            'PORT': '${toString cfg.database.port}',
            'OPTIONS': {
                'sslmode': '${cfg.database.sslMode}',
            },
        }
    }

    # Security Settings
    SECRET_KEY = open('${cfg.api.djangoSecretKeyFile}').read().strip()
    DEBUG = ${if cfg.api.djangoDebug then "True" else "False"}
    ALLOWED_HOSTS = ${builtins.toJSON cfg.api.djangoAllowedHosts}

    # CORS Settings
    ${if cfg.api.corsAllowedOrigins != [] then ''
    CORS_ALLOWED_ORIGINS = ${builtins.toJSON cfg.api.corsAllowedOrigins}
    CORS_ALLOW_CREDENTIALS = True
    '' else ""}

    # Internationalization
    TIME_ZONE = '${cfg.api.timeZone}'
    LANGUAGE_CODE = '${cfg.api.language}'

    # Logging Configuration
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
            },
        },
        'root': {
            'handlers': ['console'],
            'level': '${cfg.api.logLevel}',
        },
    }

    # File Upload Settings
    DATA_UPLOAD_MAX_MEMORY_SIZE = ${toString (
      let
        sizeStr   = cfg.api.maxRequestSize;
        parseSize = size:
          if hasSuffix "G" size then (lib.toInt (removeSuffix "G" size)) * 1073741824
          else if hasSuffix "M" size then (lib.toInt (removeSuffix "M" size)) * 1048576
          else if hasSuffix "K" size then (lib.toInt (removeSuffix "K" size)) * 1024
          else lib.toInt size;
      in parseSize sizeStr
    )}

    # Central Nodes Configuration
    ${lib.optionalString (cfg.api.extraSettings.CENTRAL_NODES or [] != []) ''
    CENTRAL_NODES = ${builtins.toJSON cfg.api.extraSettings.CENTRAL_NODES}
    ''}
    
    # Node Type Configuration
    IS_CENTRAL_NODE = ${if (cfg.api.extraSettings.IS_CENTRAL_NODE or false) then "True" else "False"}
    
    # Additional custom settings
    ${lib.concatStringsSep "\n" 
      (lib.mapAttrsToList 
        (name: value: 
          if name != "CENTRAL_NODES" && name != "IS_CENTRAL_NODE" then
            "${name} = ${if builtins.isString value then "'${value}'" else builtins.toJSON value}"
          else ""
        ) 
        (cfg.api.extraSettings)
      )
    }
  '';

  runLocalEndoApiScript = pkgs.writeShellScriptBin "${scriptName}" ''
    set -euo pipefail
    
    # Debug mode flag - controls verbose logging
    DEBUG_MODE=${if cfg.debugMode then "true" else "false"}
    
    echo "Starting EndoReg API service..."
    echo "Repository: ${gitURL}"
    echo "Branch: ${branchName}"
    echo "Target Directory: ${repoDir}"
    
    # Clone or update repository
    if [ ! -d ${repoDir} ]; then
      echo "Cloning repository..."
      git clone ${gitURL} ${repoDir}
      cd ${repoDir}
    else
      cd ${repoDir}
      ${if cfg.repository.updateOnBoot then ''
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
    
    ${if cfg.repository.updateOnBoot then ''
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

    echo "Initializing submodules..."
    git submodule init || { echo "ERROR: Failed to initialize submodules"; exit 1; }
    git submodule update --remote --recursive || { echo "ERROR: Failed to update submodules"; exit 1; }
    git submodule init
    git submodule update --remote --recursive

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
    
    # Ensure conf directory exists (it might be in .gitignore)
    mkdir -p ${envConfDir}
    
    if [ -f "$SECRET_FILE" ] && head -c 1 "$SECRET_FILE" >/dev/null 2>&1; then
      cp "$SECRET_FILE" ${envConfDir}/db_pwd
      echo "Database password copied from vault to ${envConfDir}/db_pwd"
      
      # Run Django application's configuration setup
      echo "Running Django application configuration setup..."
      cd ${repoDir}
      
      # Set environment variables needed by the Django config scripts
      export DATA_DIR="${envDataDir}"
      export CONF_DIR="${envConfDir}"
      export CONF_TEMPLATE_DIR="${envConfTemplateDir}"
      export DJANGO_MODULE="${envDjangoModule}"
      export HTTP_PROTOCOL="${envHttpProtocol}"
      export DJANGO_HOST="${envDjangoHost}"
      export DJANGO_PORT="${envDjangoPort}"
      export BASE_URL="${envBaseUrl}"
      
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
      else
        echo "devenv not available, trying direct script execution..."
        if [ -f "scripts/make_conf.py" ]; then
          python scripts/make_conf.py || echo "WARNING: make_conf.py execution failed"
        else
          echo "WARNING: scripts/make_conf.py not found"
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
    
    # Create a local copy outside the git repository to avoid conflicts
    echo "Copying Django configuration file..."
    # Remove existing file if it exists (it might be read-only)
    if [ -f "$CONFIG_DIR/local_settings.py" ]; then
      echo "Removing existing local_settings.py file"
      rm -f "$CONFIG_DIR/local_settings.py" || { 
        echo "Existing file is read-only, making it writable first"
        chmod +w "$CONFIG_DIR/local_settings.py" 2>/dev/null || true
        rm -f "$CONFIG_DIR/local_settings.py"
      }
    fi
    cp ${djangoConfigFile} "$CONFIG_DIR/local_settings.py" || { 
      echo "ERROR: Failed to copy Django configuration to $CONFIG_DIR/local_settings.py"
      echo "Directory permissions:"
      ls -la "$CONFIG_DIR" 2>/dev/null || echo "Cannot access $CONFIG_DIR"
      ls -la "${endoreg-service-user-home}" 2>/dev/null || echo "Cannot access ${endoreg-service-user-home}"
      exit 1
    }
    echo "Django configuration copied to $CONFIG_DIR/local_settings.py"
    
    # Create symlink in the repository (remove existing symlink first if it exists)
    if [ -L ${repoDir}/local_settings.py ]; then
      rm ${repoDir}/local_settings.py
    fi
    ln -sf "$CONFIG_DIR/local_settings.py" ${repoDir}/local_settings.py || { echo "ERROR: Failed to create symlink"; exit 1; }
    echo "Created symlink: ${repoDir}/local_settings.py -> $CONFIG_DIR/local_settings.py"

    ${lib.optionalString (cfg.service.extraEnvironment != {}) ''
    # Set additional environment variables
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: value: "export ${name}='${value}'") cfg.service.extraEnvironment)}
    ''}

    echo "Starting Django server..."
    echo "Hostname: ${envDjangoHost}"
    echo "Port: ${envDjangoPort}"
    echo "Protocol: ${envHttpProtocol}"
    
    # Start the Django application
    exec devenv shell -- run-prod-server
  '';

in
{
  options.services.luxnix.endoregDbApiLocal = {
    enable = mkBoolOpt false "Enable EndoRegDbApi Service";

    # Configuration options (passed from endoreg-client role)
    api = mkOption {
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
          timeZone = mkOption { type = types.str; default = "UTC"; };
          language = mkOption { type = types.str; default = "en-us"; };
          
          # Environment variable configuration options
          dataDir = mkOption { 
            type = types.str; 
            default = "data"; 
            description = "Relative path to data directory within the repository";
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
            default = "endo_api"; 
            description = "Django module name for the application";
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
          
          extraSettings = mkOption { 
            type = types.attrsOf types.anything; 
            default = {}; 
            description = "Additional settings to pass to Django configuration";
          };
        };
      };
      default = {};
      description = "API configuration options";
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

    service = mkOption {
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
      description = "Service configuration options";
    };

    repository = mkOption {
      type = types.submodule {
        options = {
          url = mkOption { type = types.str; default = "https://github.com/wg-lux/endo-api"; };
          branch = mkOption { type = types.str; default = "main"; };
          updateOnBoot = mkOption { type = types.bool; default = true; };
        };
      };
      default = {};
      description = "Repository configuration options";
    };

    debugMode = mkOption {
      type = types.bool;
      default = false;
      description = "Enable verbose debug output including sensitive file information. Should be disabled in production.";
    };
  };

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
    
    systemd.services."endo-api-boot" = {
      description = "Clone or pull endoreg-db-api and run prod-server";
      wantedBy = [ "multi-user.target" ];
      after = [ "postgres-endoreg-setup.service" "endoreg-django-setup.service" "systemd-tmpfiles-setup.service" ];
      requires = [ "postgres-endoreg-setup.service" "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        Environment = "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:/run/current-system/sw/bin";
        ExecStart = "${runLocalEndoApiScript}/bin/${scriptName}";
        Restart = "on-failure";
        RestartSec = "10s";
        # Resource limits
        MemoryMax = "2G";
        CPUQuota = "200%";
      };
    };
  };
}
