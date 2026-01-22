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
  sslCfg = lib.attrByPath [ "services" "luxnix" "lxSsl" ]
    {
      enable = false;
      sslDir = "/var/lib/lx-annotate/ssl";
      certPath = "/var/lib/lx-annotate/ssl/lx-annotate-selfsigned.crt";
      keyPath = "/var/lib/lx-annotate/ssl/lx-annotate-selfsigned.key";
    }
    config;

  defaultSslCertificatePath = sslCfg.certPath;
  defaultSslKeyPath = sslCfg.keyPath;

  adminName = config.user.admin.name;
  scriptName = "runLocalLxAnnotate";

  # Use configuration options from new structure
  gitURL = cfg.source.url;
  repoDirName = "lx-annotate";
  branchName = cfg.source.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  endoreg-service-group-name = config.user.endoreg-service-user.group;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";
  staticRootPath = "${repoDir}/static";

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
  sslDir = sslCfg.sslDir;
  sslKeyPath = sslCfg.keyPath;
  sslCertPath = sslCfg.certPath;

  makeAbsolute = path: if lib.hasPrefix "/" path then path else "${repoDir}/${path}";

  envAssetDir = makeAbsolute cfg.django.assetDir;
  envStaticUrl = cfg.django.staticUrl;
  envMediaUrl = cfg.django.mediaUrl;
  envRunVideoTests = if cfg.django.runVideoTests then "true" else "false";
  envSkipExpensiveTests = if cfg.django.skipExpensiveTests then "true" else "false";

  settingsProfile = cfg.django.settingsProfile;
  envIsCentralNode = cfg.django.extraSettings.IS_CENTRAL_NODE or false;
  envAnnotateDjangoSettingsModule = "lx_annotate.settings.settings_prod";
  envDjangoEnv = "production";
  envCentralNodeFlag = if envIsCentralNode || settingsProfile == "central" then "true" else "false";

  # Default center from django extraSettings
  envDefaultCenter = cfg.django.extraSettings.DEFAULT_CENTER or "university_hospital_wuerzburg";

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
          cd ${repoDir}
          direnv allow
        else
          cd ${repoDir}
          ${if cfg.source.updateOnBoot then ''
            echo "Updating repository..."
            git fetch origin ${branchName} || { echo "ERROR: Failed to fetch from origin"; exit 1; }
          '' else ''
            echo "Repository update disabled"
          ''}
        fi

        # Checkout branch
        echo "Checking out branch: ${branchName}"
        if git show-ref --verify --quiet refs/heads/${branchName}; then
          git checkout ${branchName} || { echo "ERROR: Checkout failed"; exit 1; }
        elif git show-ref --verify --quiet refs/remotes/origin/${branchName}; then
          git checkout -b ${branchName} origin/${branchName} || { echo "ERROR: Tracking branch failed"; exit 1; }
        else
          echo "ERROR: Branch ${branchName} does not exist"
          exit 1
        fi

        ${if cfg.source.updateOnBoot then ''
        # Update branch
        git pull origin ${branchName} || { 
          echo "WARNING: Failed to pull, trying reset"
          git reset --hard origin/${branchName} || { echo "ERROR: Update failed"; exit 1; }
        }
        '' else ""}

        # --- DB SETUP ---
        cd ${repoDir}
        direnv allow

        mkdir -p ${envConfDir} ${envDataDir}


        # --- ENV SETUP ---
        echo "Running Django application configuration setup..."
        cd ${repoDir}
    
        export DJANGO_DB_PASSWORD_FILE="${cfg.database.endoregLocalUserPasswordFile}" 
        export DJANGO_SECRET_KEY_FILE="${cfg.django.djangoSecretKeyFile}"
        export OIDC_RP_CLIENT_SECRET_FILE="${cfg.django.keycloakSecretFile}"
    
        export DATA_DIR="${envDataDir}"
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
        export STATIC_URL="${envStaticUrl}"
        export MEDIA_URL="${envMediaUrl}"
        export ASSET_DIR="${envAssetDir}"
        export RUN_VIDEO_TESTS="${envRunVideoTests}"
        export SKIP_EXPENSIVE_TESTS="${envSkipExpensiveTests}"
        export EXEMPT_URLS="^/accounts/login/$"
        export LOGIN_URL="/accounts/login/"

        DJANGO_DB_PASSWORD_VALUE="$(tr -d '\n' < ${envConfDir}/db_pwd 2>/dev/null || true)"
        export DJANGO_DB_ENGINE="django.db.backends.postgresql"
        export DJANGO_DB_NAME="${cfg.database.name}"
        export DJANGO_DB_USER="${cfg.database.user}"
        export DJANGO_DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD_VALUE"
        export DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD_VALUE"
        export DJANGO_DB_HOST="${cfg.database.host}"
        export DJANGO_DB_PORT="${toString cfg.database.port}"
        export DJANGO_DB_SSLMODE="${cfg.database.sslMode}"
    
        export DJANGO_ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
        export ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
        export DJANGO_CORS_ALLOWED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
        export DJANGO_CSRF_TRUSTED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
    
        DJANGO_SECRET_KEY_VALUE="$(tr -d '\n' < ${cfg.django.djangoSecretKeyFile} 2>/dev/null || true)"
        export DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY_VALUE"

        export OIDC_RP_CLIENT_ID="${cfg.django.keycloakClientId}"
        OIDC_CLIENT_SECRET_VALUE="$(tr -d '\n' < ${cfg.django.keycloakSecretFile} 2>/dev/null || true)"
        export OIDC_RP_CLIENT_SECRET="$OIDC_CLIENT_SECRET_VALUE"    

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
    profile = "default"
    EOF

        echo "Collecting static files..."
    echo "Collecting static files..."
        export DJANGO_STATIC_ROOT="${staticRootPath}" # This points to .../staticfiles

        if command -v devenv >/dev/null 2>&1; then
           # 1. Add this command here
           devenv shell -- python manage.py collectstatic --noinput --clear
       
           echo "Running Database Migrations..."
           devenv shell -- python manage.py migrate --noinput
           devenv shell -- python manage.py load_base_db_data
        else
           source .venv/bin/activate 
       
           # 2. And add it here for non-devenv setups
           python manage.py collectstatic --noinput --clear

           echo "Running Database Migrations..."
           python manage.py migrate --noinput
           python manage.py load_base_db_data
        fi

        echo "Starting Django server..."


        echo "Starting Django server..."
    
        # Write essential environment variables to .env.systemd
    cat > ${repoDir}/.env.systemd <<EOF
    HOME_DIR=${endoreg-service-user-home}
    DATA_DIR=${envDataDir}
    CONF_DIR=${envConfDir}
    CONF_TEMPLATE_DIR=${envConfTemplateDir}
    WORKING_DIR=${repoDir}
    DJANGO_STATIC_ROOT=${staticRootPath}

    # --- Network & Host Configuration ---
    HTTP_PROTOCOL=${envHttpProtocol}
    DJANGO_HOST=${envDjangoHost}
    DJANGO_PORT=${envDjangoPort}
    BASE_URL=${envBaseUrl}
    DJANGO_ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
    ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
    DJANGO_CSRF_TRUSTED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'
    EOF

        # build the environment and start the server
        exec devenv shell -- bash -c "vue-build && run-server"
  '';
  watcherScriptName = "runLocalFileWatcher";
  runLocalFileWatcherScript = pkgs.writeShellScriptBin "${watcherScriptName}" ''
    set -euo pipefail
    
    # 1. Go to the repo (Cloned by the main boot service)
    cd ${repoDir}

    # 2. Re-Export ALL necessary Environment Variables
    # (Note: We skip git clone/pull because the boot service handles that)
    
    export DJANGO_DB_PASSWORD_FILE="${cfg.database.endoregLocalUserPasswordFile}" 
    export DJANGO_SECRET_KEY_FILE="${cfg.django.djangoSecretKeyFile}"
    export DATA_DIR="${envDataDir}"
    export CONF_DIR="${envConfDir}"
    export DJANGO_MODULE="${envDjangoModule}"
    export DJANGO_SETTINGS_MODULE="lx_annotate.settings.settings_prod"
    export DJANGO_ENV="${envDjangoEnv}"
    export CENTRAL_NODE="${envCentralNodeFlag}"
    export HTTP_PROTOCOL="${envHttpProtocol}"
    export DJANGO_HOST="${envDjangoHost}"
    export DJANGO_PORT="${envDjangoPort}"
    export BASE_URL="${envBaseUrl}"
    export TIME_ZONE="${cfg.django.timeZone}"
    export RUN_VIDEO_TESTS="${envRunVideoTests}"
    export SKIP_EXPENSIVE_TESTS="${envSkipExpensiveTests}"

    # 3. Read Secrets (Must match boot script logic)
    DJANGO_DB_PASSWORD_VALUE="$(tr -d '\n' < ${envConfDir}/db_pwd 2>/dev/null || true)"
    export DJANGO_DB_ENGINE="django.db.backends.postgresql"
    export DJANGO_DB_NAME="${cfg.database.name}"
    export DJANGO_DB_USER="${cfg.database.user}"
    export DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD_VALUE"
    export DJANGO_DB_HOST="${cfg.database.host}"
    export DJANGO_DB_PORT="${toString cfg.database.port}"
    export DJANGO_DB_SSLMODE="${cfg.database.sslMode}"
    
    DJANGO_SECRET_KEY_VALUE="$(tr -d '\n' < ${cfg.django.djangoSecretKeyFile} 2>/dev/null || true)"
    export DJANGO_SECRET_KEY="$DJANGO_SECRET_KEY_VALUE"
    HOME_DIR=${endoreg-service-user-home}
    DATA_DIR=${envDataDir}
    CONF_DIR=${envConfDir}
    CONF_TEMPLATE_DIR=${envConfTemplateDir}
    WORKING_DIR=${repoDir}
    DJANGO_STATIC_ROOT=${staticRootPath}

    # --- Network & Host Configuration ---
    HTTP_PROTOCOL=${envHttpProtocol}
    DJANGO_HOST=${envDjangoHost}
    DJANGO_PORT=${envDjangoPort}
    BASE_URL=${envBaseUrl}
    DJANGO_ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
    ALLOWED_HOSTS='${builtins.toJSON cfg.django.djangoAllowedHosts}'
    DJANGO_CSRF_TRUSTED_ORIGINS='${builtins.toJSON cfg.django.corsAllowedOrigins}'

    # 4. Start the Watcher inside the devenv shell
    echo "📁 Starting File Watcher..."
    
    # Check if devenv is available in path (it is set in Service Config)
    exec devenv shell -- bash -c start-filewatcher 
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
        options = {
          hostname = mkOption { type = types.str; default = "lx-annotate.local"; };
          port = mkOption { type = types.port; default = 8117; };
          useHttps = mkOption { type = types.bool; default = false; };
          sslCertificatePath = mkOption { type = types.nullOr types.path; default = null; };
          sslKeyPath = mkOption { type = types.nullOr types.path; default = null; };
          djangoAllowedHosts = mkOption {
            type = types.listOf types.str;
            default = [ "lx-annotate.local" "127.0.0.1" ]; # NO http://
          };

          corsAllowedOrigins = mkOption {
            type = types.listOf types.str;
            default = [ "https://lx-annotate.local" "http://127.0.0.1" ];
          };
          djangoDebug = mkOption { type = types.bool; default = false; };
          djangoSecretKeyFile = mkOption { type = types.path; default = "/etc/secrets/vault/django_secret_key"; };

          keycloakSecretFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/keycloak.env";
            description = "Path to file containing the Keycloak Client Secret.";
          };

          keycloakClientId = mkOption {
            type = types.str;
            default = "endoregdb-api";
            description = "Keycloak Client ID.";
          };
          # -------------------------------

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
            default = { };
            description = "Additional settings to pass to Django configuration";
          };
        };
      };
      default = { };
      description = "Django configuration options for lx-annotate.";
    };

    # Database configuration
    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption { type = types.str; default = "lx-annotate.local"; };
          port = mkOption { type = types.port; default = 5433; };
          name = mkOption { type = types.str; default = "lxAnnotateLocal"; };
          user = mkOption { type = types.str; default = "lxAnnotateLocal"; };
          passwordFile = mkOption { type = types.path; default = "/etc/secrets/vault/SCRT_local_password_maintenance_password"; };
          sslMode = mkOption { type = types.str; default = "prefer"; };
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

  config = {
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
        '' + optionalString sslCfg.enable ''
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

    systemd.tmpfiles.rules =
      [
        "d ${endoreg-service-user-home} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

        # Ensure the main repo directory exists (if not cloned yet, this sets the parent permissions)
        "d ${repoDir} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

        # Explicitly create the data/storage directories so Python doesn't have to fight for permissions
        "d ${envDataDir} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

        # Ensure static dir exists for nginx alias
        "d ${staticRootPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
        
        # 1. The Parent Directory: Create (d) AND Enforce (z) permissions
        "d /var/lib/lx-annotate 0750 root nginx - -"
        "z /var/lib/lx-annotate 0750 root nginx - -"
        
        # 2. The SSL Directory: Create (d) AND Enforce (z) permissions
        "d /var/lib/lx-annotate/ssl 0750 root nginx - -"
        "z /var/lib/lx-annotate/ssl 0750 root nginx - -"
        
        # 3. The Certificate Files: Recursively fix perms
        "Z /var/lib/lx-annotate/ssl 0640 root nginx - -"
      ]
      ++ lib.optionals (!config.roles.endoreg-client.enable) [
        # Create the config subdirectory (handled by endoreg-client role when enabled)
        "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      ];

    systemd.services."lx-annotate-boot" = {
      description = "Clone or pull lx-annotate and run prod-server";
      wantedBy = [ "multi-user.target" ];
      wants = [ "nginx.service" "postgres-endoreg-setup.service" ];
      after = [ "postgres-endoreg-setup.service" "endoreg-django-setup.service" "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
        ExecStartPre = "+${pkgs.writeShellScript "lx-annotate-pre-start" ''
            set -euo pipefail
            
            # 1. Fix Repo Permissions
            ${pkgs.coreutils}/bin/chown -R ${endoreg-service-user-name}:${endoreg-service-group-name} ${repoDir}
            
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
        RestartSec = "10s";
        # Resource limits
        MemoryMax = "8G";
        CPUQuota = "800%";
      };
    };
    systemd.services.lx-annotate-filewatcher = {
      description = "Django File Watcher Service";
      wantedBy = [ "multi-user.target" ];
      after = [ "postgresql.service" ]; # Adjust based on your DB
      requires = [ "lx-annotate-boot.service" ];


      serviceConfig = {
        User = config.user.endoreg-service-user.name; # Or whatever user runs the app
        WorkingDirectory = repoDir;
        ExecStart = "${runLocalFileWatcherScript}/bin/${watcherScriptName}";        
        Restart = "on-failure";
        RestartSec = "10s";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];
      };
    };
  };
}