{ lib
, config
, pkgs
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.endoreg-client;


  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
in
{
  options.roles.endoreg-client = {
    enable = mkEnableOption "Enable endoreg client configuration";

    # Central Nodes Configuration
    centralNodes = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "List of hostnames that act as central nodes for the endoreg database API";
      example = [ "s-04.local" "backup-central.local" ];
    };

    dbApiLocal = mkOption {
      type = types.bool;
      default = false;
      description = "Enable local endoreg-db-api service";
    };

    endoAi = mkOption {
      type = types.bool;
      default = false;
      description = "Enable endoAi service";
    };

    # Django API Configuration Options
    api = {
      hostname = mkOption {
        type = types.str;
        default = "localhost";
        description = "Hostname for the Django API service";
        example = "api.example.com";
      };

      port = mkOption {
        type = types.port;
        default = 8118;
        description = "Port for the Django API service";
      };

      useHttps = mkOption {
        type = types.bool;
        default = false;
        description = "Whether to use HTTPS for the API service";
      };

      sslCertificatePath = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to SSL certificate file (required if useHttps is true)";
        example = "/etc/secrets/ssl/api.crt";
      };

      sslKeyPath = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to SSL private key file (required if useHttps is true)";
        example = "/etc/secrets/ssl/api.key";
      };

      djangoAllowedHosts = mkOption {
        type = types.listOf types.str;
        default = [ "localhost" "127.0.0.1" ];
        description = "Django ALLOWED_HOSTS setting";
        example = [ "api.example.com" "localhost" "127.0.0.1" ];
      };

      djangoDebug = mkOption {
        type = types.bool;
        default = false;
        description = "Enable Django DEBUG mode (should be false in production)";
      };

      djangoSecretKeyFile = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/django_secret_key";
        description = "Path to file containing Django SECRET_KEY";
      };

      corsAllowedOrigins = mkOption {
        type = types.listOf types.str;
        default = [];
        description = "CORS allowed origins for the API";
        example = [ "https://frontend.example.com" "http://localhost:3000" ];
      };

      logLevel = mkOption {
        type = types.enum [ "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL" ];
        default = "INFO";
        description = "Django logging level";
      };

      maxRequestSize = mkOption {
        type = types.str;
        default = "100M";
        description = "Maximum request size for file uploads";
      };

      timeZone = mkOption {
        type = types.str;
        default = "UTC";
        description = "Django timezone setting";
        example = "Europe/Berlin";
      };

      language = mkOption {
        type = types.str;
        default = "en-us";
        description = "Django language setting";
        example = "de-de";
      };
    };

    # lxAnnotate = {};

    # Database Configuration Options
    database = {
      host = mkOption {
        type = types.str;
        default = "localhost";
        description = "PostgreSQL database host";
      };

      port = mkOption {
        type = types.port;
        default = 5432;
        description = "PostgreSQL database port";
      };

      name = mkOption {
        type = types.str;
        default = "endoregDbLocal";
        description = "PostgreSQL database name";
      };

      user = mkOption {
        type = types.str;
        default = "endoregDbLocal";
        description = "PostgreSQL database user";
      };

      passwordFile = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
        description = "Path to file containing database password";
      };

      sslMode = mkOption {
        type = types.enum [ "disable" "allow" "prefer" "require" "verify-ca" "verify-full" ];
        default = "prefer";
        description = "PostgreSQL SSL mode";
      };
    };

    # Service Configuration Options
    service = {
      workers = mkOption {
        type = types.int;
        default = 1;
        description = "Number of worker processes for the API service";
      };

      maxRequests = mkOption {
        type = types.int;
        default = 1000;
        description = "Maximum requests per worker before restart";
      };

      timeout = mkOption {
        type = types.int;
        default = 30;
        description = "Request timeout in seconds";
      };

      keepAlive = mkOption {
        type = types.int;
        default = 60;
        description = "Keep-alive timeout in seconds";
      };

      extraEnvironment = mkOption {
        type = types.attrsOf types.str;
        default = {};
        description = "Additional environment variables for the service";
        example = {
          REDIS_URL = "redis://localhost:6379/0";
          CELERY_BROKER_URL = "redis://localhost:6379/1";
        };
      };
    };

    # Git Repository Options
    repository = {
      url = mkOption {
        type = types.str;
        default = "https://github.com/wg-lux/endo-api";
        description = "Git repository URL for the Django API";
      };

      branch = mkOption {
        type = types.str;
        default = "main";
        description = "Git branch to checkout";
      };

      updateOnBoot = mkOption {
        type = types.bool;
        default = true;
        description = "Whether to update the repository on service start";
      };
    };
  };

  config = mkIf cfg.enable {
    user.endoreg-service-user.enable = true;
    group.endoreg-service.enable = true;  # Ensure the group is created

    roles = {
      desktop.enable = true;
      custom-packages.cuda = true;
      aglnet.client.enable = true;
    };

    luxnix.nvidia-prime.enable = true;

    services.luxnix.endoregDbApiLocal = mkIf (!config.roles.endoreg-db-central-01.enable) {
      enable = mkDefault cfg.dbApiLocal;
      
      # Pass configuration options to the service
      api = cfg.api // {
        # Add central nodes information
        extraSettings = {
          CENTRAL_NODES = cfg.centralNodes;
          IS_CENTRAL_NODE = false;
        };
      };
      database = cfg.database;
      service = cfg.service;
      repository = cfg.repository;
    };

    services.luxnix.endoAi = {
      enable = cfg.endoAi;
    };

    # Create additional systemd tmpfiles for configuration
    systemd.tmpfiles.rules = [
      # USB Encrypter
      "d /mnt/endoreg-sensitive-data 0770 root ${sensitiveServiceGroupName} -"
      # Django configuration directory
      "d /etc/endoreg-api 0755 root root -"
      # Service user config directory
      "d /var/endoreg-service-user/config 0755 endoreg-service-user endoreg-service -"
    ];

    # Generate Django secret key if it doesn't exist
    systemd.services.endoreg-django-setup = mkIf cfg.dbApiLocal {
      description = "Django configuration setup (handled by managed-secrets)";
      wantedBy = [ "multi-user.target" ];
      before = [ "endo-api-boot.service" ];
      after = [ "managed-secrets-setup.service" ];
      requires = [ "managed-secrets-setup.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        ExecStart = pkgs.writeShellScript "setup-django-config" ''
          set -euo pipefail
          
          # Verify that Django secret key exists (should be created by managed-secrets)
          if [ ! -f ${cfg.api.djangoSecretKeyFile} ]; then
            echo "ERROR: Django secret key not found at ${cfg.api.djangoSecretKeyFile}"
            echo "This should have been created by managed-secrets-setup.service"
            exit 1
          fi
          
          # Ensure correct permissions (managed-secrets should handle this, but double-check)
          chmod 640 ${cfg.api.djangoSecretKeyFile}
          chown root:${sensitiveServiceGroupName} ${cfg.api.djangoSecretKeyFile}
          
          echo "Django configuration verification completed"
        '';
      };
    };
  };
}
