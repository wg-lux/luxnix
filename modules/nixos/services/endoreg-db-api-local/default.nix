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
  gitURL = cfg.repository.url or "https://github.com/wg-lux/endo-api";
  repoDirName = "endo-api";
  branchName = cfg.repository.branch or "main";

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";

  # Django configuration file
  djangoConfigFile = pkgs.writeText "django-local-settings.py" ''
    # Auto-generated Django configuration for endoreg-api
    import os
    from pathlib import Path

    # Database Configuration
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': '${cfg.database.name or "endoregDbLocal"}',
            'USER': '${cfg.database.user or "endoregDbLocal"}',
            'PASSWORD': open('${cfg.database.passwordFile or "/etc/secrets/vault/SCRT_local_password_maintenance_password"}').read().strip(),
            'HOST': '${cfg.database.host or "localhost"}',
            'PORT': '${toString (cfg.database.port or 5432)}',
            'OPTIONS': {
                'sslmode': '${cfg.database.sslMode or "prefer"}',
            },
        }
    }

    # Security Settings
    SECRET_KEY = open('${cfg.api.djangoSecretKeyFile or "/etc/secrets/vault/django_secret_key"}').read().strip()
    DEBUG = ${if (cfg.api.djangoDebug or false) then "True" else "False"}
    ALLOWED_HOSTS = ${builtins.toJSON (cfg.api.djangoAllowedHosts or ["localhost" "127.0.0.1"])}

    # CORS Settings
    ${if (cfg.api.corsAllowedOrigins or []) != [] then ''
    CORS_ALLOWED_ORIGINS = ${builtins.toJSON cfg.api.corsAllowedOrigins}
    CORS_ALLOW_CREDENTIALS = True
    '' else ""}

    # Internationalization
    TIME_ZONE = '${cfg.api.timeZone or "UTC"}'
    LANGUAGE_CODE = '${cfg.api.language or "en-us"}'

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
            'level': '${cfg.api.logLevel or "INFO"}',
        },
    }

    # File Upload Settings
    DATA_UPLOAD_MAX_MEMORY_SIZE = ${toString (
      let
        sizeStr   = cfg.api.maxRequestSize or "100M";
        parseSize = size:
          if hasSuffix "G" size then (lib.toInt (removeSuffix "G" size)) * 1073741824
          else if hasSuffix "M" size then (lib.toInt (removeSuffix "M" size)) * 1048576
          else if hasSuffix "K" size then (lib.toInt (removeSuffix "K" size)) * 1024
          else lib.toInt size;
      in parseSize sizeStr
    )}

    # Central Nodes Configuration
    ${lib.optionalString ((cfg.api.extraSettings.CENTRAL_NODES or []) != []) ''
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
        (cfg.api.extraSettings or {})
      )
    }
  '';

  runLocalEndoApiScript = pkgs.writeShellScriptBin "${scriptName}" ''
    set -euo pipefail
    
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
      ${if (cfg.repository.updateOnBoot or true) then ''
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
    
    ${if (cfg.repository.updateOnBoot or true) then ''
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
    echo "Current user: $(whoami)"
    echo "User groups: $(groups)"
    echo "Checking for database password file: ${cfg.database.passwordFile or "/etc/secrets/vault/SCRT_local_password_maintenance_password"}"
    
    # Debug secret file access
    SECRET_FILE="${cfg.database.passwordFile or "/etc/secrets/vault/SCRT_local_password_maintenance_password"}"
    if [ -f "$SECRET_FILE" ]; then
      echo "Secret file exists: $SECRET_FILE"
      ls -la "$SECRET_FILE" || echo "Cannot stat secret file"
      echo "Testing read access..."
      if head -c 10 "$SECRET_FILE" >/dev/null 2>&1; then
        echo "✓ Can read secret file"
      else
        echo "✗ Cannot read secret file"
        echo "File permissions:"
        ls -la "$SECRET_FILE" 2>/dev/null || echo "Cannot access file"
        echo "Directory permissions:"
        ls -la "$(dirname "$SECRET_FILE")" 2>/dev/null || echo "Cannot access directory" 
        echo "Parent directory permissions:"
        ls -la "/etc/secrets" 2>/dev/null || echo "Cannot access /etc/secrets"
      fi
    else
      echo "Secret file does not exist: $SECRET_FILE"
      echo "Directory contents:"
      ls -la "$(dirname "$SECRET_FILE")" 2>/dev/null || echo "Cannot access $(dirname "$SECRET_FILE")"
      ls -la "/etc/secrets" 2>/dev/null || echo "Cannot access /etc/secrets"
    fi
    
    # Ensure conf directory exists (it might be in .gitignore)
    mkdir -p ${repoDir}/conf
    
    if [ -f "$SECRET_FILE" ] && head -c 1 "$SECRET_FILE" >/dev/null 2>&1; then
      cp "$SECRET_FILE" ${repoDir}/conf/db_pwd
      echo "Database password copied from vault to ${repoDir}/conf/db_pwd"
      
      # Run Django application's configuration setup
      echo "Running Django application configuration setup..."
      cd ${repoDir}
      
      # Set environment variables needed by the Django config scripts
      #TODO QUICK FIX, Improve
      export DATA_DIR="${repoDir}/data"
      export CONF_DIR="${repoDir}/conf"
      export CONF_TEMPLATE_DIR="${repoDir}/conf_template"
      export DJANGO_MODULE="endo_api"
      export HTTP_PROTOCOL="http"
      export DJANGO_HOST="localhost"
      export DJANGO_PORT="8118"
      export BASE_URL="http://localhost:8118"
      
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
      if [ -f "${repoDir}/conf/db.yaml" ]; then
        echo "✓ Django configuration file created: ${repoDir}/conf/db.yaml"
      else
        echo "WARNING: Django configuration file ${repoDir}/conf/db.yaml was not created"
        echo "Contents of conf directory:"
        ls -la "${repoDir}/conf/" 2>/dev/null || echo "Cannot access conf directory"
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

    ${lib.optionalString ((cfg.service.extraEnvironment or {}) != {}) ''
    # Set additional environment variables
    ${lib.concatStringsSep "\n" (lib.mapAttrsToList (name: value: "export ${name}='${value}'") cfg.service.extraEnvironment)}
    ''}

    echo "Starting Django server..."
    echo "Hostname: ${cfg.api.hostname or "localhost"}"
    echo "Port: ${toString (cfg.api.port or 8118)}"
    echo "Protocol: ${if (cfg.api.useHttps or false) then "HTTPS" else "HTTP"}"
    
    # Start the Django application
    exec devenv shell -- run-prod-server
  '';

in
{
  options.services.luxnix.endoregDbApiLocal = {
    enable = mkBoolOpt false "Enable EndoRegDbApi Service";

    # Configuration options (passed from endoreg-client role)
    api = mkOption {
      type = types.nullOr (types.submodule {
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
          extraSettings = mkOption { 
            type = types.attrsOf types.anything; 
            default = {}; 
            description = "Additional settings to pass to Django configuration";
          };
        };
      });
      default = null;
      description = "API configuration options";
    };

    database = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          host = mkOption { type = types.str; default = "localhost"; };
          port = mkOption { type = types.port; default = 5432; };
          name = mkOption { type = types.str; default = "endoregDbLocal"; };
          user = mkOption { type = types.str; default = "endoregDbLocal"; };
          passwordFile = mkOption { type = types.path; default = "/etc/secrets/vault/SCRT_local_password_maintenance_password"; };
          sslMode = mkOption { type = types.str; default = "prefer"; };
        };
      });
      default = null;
      description = "Database configuration options";
    };

    service = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          workers = mkOption { type = types.int; default = 1; };
          maxRequests = mkOption { type = types.int; default = 1000; };
          timeout = mkOption { type = types.int; default = 30; };
          keepAlive = mkOption { type = types.int; default = 60; };
          extraEnvironment = mkOption { type = types.attrsOf types.str; default = {}; };
        };
      });
      default = null;
      description = "Service configuration options";
    };

    repository = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          url = mkOption { type = types.str; default = "https://github.com/wg-lux/endo-api"; };
          branch = mkOption { type = types.str; default = "main"; };
          updateOnBoot = mkOption { type = types.bool; default = true; };
        };
      });
      default = null;
      description = "Repository configuration options";
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
