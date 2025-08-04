{ lib
, config
, pkgs
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.endoreg-db-central-01;

  sensitiveServiceGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;
in
{
  options.roles.endoreg-db-central-01 = {
    enable = mkEnableOption "Enable endoreg database central node configuration";

    # Central Node Configuration
    centralNodes = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "List of hostnames that act as central nodes for the endoreg database API";
      example = [ "s-04.local" "backup-central.local" ];
    };

    # Local Node Configuration  
    localNodes = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "List of hostnames that have local endoreg database API instances";
      example = [ "gc-10.local" "gs-01.local" ];
    };

    # API Configuration for Central Node
    api = {
      hostname = mkOption {
        type = types.str;
        default = "0.0.0.0";  # Listen on all interfaces for central node
        description = "Hostname for the central Django API service";
        example = "0.0.0.0";
      };

      port = mkOption {
        type = types.port;
        default = 8118;
        description = "Port for the central Django API service";
      };

      useHttps = mkOption {
        type = types.bool;
        default = true;  # Central nodes should use HTTPS
        description = "Whether to use HTTPS for the central API service";
      };

      sslCertificatePath = mkOption { #ALREADY CENTRALLY AVAILABLE SOMEWHERE, Refactor to use available implementation here
        type = types.nullOr types.path;
        default = null;
        description = "Path to SSL certificate file (required if useHttps is true)";
        example = "/etc/secrets/ssl/central-api.crt";
      };

      sslKeyPath = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to SSL private key file (required if useHttps is true)";
        example = "/etc/secrets/ssl/central-api.key";
      };

      djangoAllowedHosts = mkOption {
        type = types.listOf types.str;
        default = [ "localhost" "127.0.0.1" ];
        description = "Django ALLOWED_HOSTS setting - will be automatically extended with local nodes";
        example = [ "s-04.local" "central-api.example.com" ];
      };

      djangoDebug = mkOption {
        type = types.bool;
        default = false;  # Production setting for central node
        description = "Enable Django DEBUG mode (should be false in production)";
      };

      djangoSecretKeyFile = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/django_central_secret_key";
        description = "Path to file containing Django SECRET_KEY for central node";
      };

      corsAllowedOrigins = mkOption {
        type = types.listOf types.str;
        default = [];
        description = "CORS allowed origins for the central API";
        example = [ "https://frontend.example.com" "http://localhost:3000" ];
      };

      logLevel = mkOption {
        type = types.enum [ "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL" ];
        default = "INFO";
        description = "Django logging level for central node";
      };

      maxRequestSize = mkOption {
        type = types.str;
        default = "500M";  # Larger for central node
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

    # Database Configuration for Central Node
    database = {
      host = mkOption {
        type = types.str;
        default = "localhost";
        description = "PostgreSQL database host for central node";
      };

      port = mkOption {
        type = types.port;
        default = 5432;
        description = "PostgreSQL database port for central node";
      };

      name = mkOption {
        type = types.str;
        default = "endoregDbCentral";
        description = "PostgreSQL database name for central node";
      };

      user = mkOption {
        type = types.str;
        default = "endoregDbCentral";
        description = "PostgreSQL database user for central node";
      };

      passwordFile = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/SCRT_central_password_maintenance_password";
        description = "Path to file containing central database password";
      };

      sslMode = mkOption {
        type = types.enum [ "disable" "allow" "prefer" "require" "verify-ca" "verify-full" ];
        default = "require";  # More secure for central node
        description = "PostgreSQL SSL mode for central node";
      };
    };

    # Service Configuration for Central Node
    service = {
      workers = mkOption {
        type = types.int;
        default = 4;  # More workers for central node
        description = "Number of worker processes for the central API service";
      };

      maxRequests = mkOption {
        type = types.int;
        default = 5000;  # Higher for central node
        description = "Maximum requests per worker before restart";
      };

      timeout = mkOption {
        type = types.int;
        default = 60;  # Longer timeout for central operations
        description = "Request timeout in seconds";
      };

      keepAlive = mkOption {
        type = types.int;
        default = 120;  # Longer keep-alive for central node
        description = "Keep-alive timeout in seconds";
      };

      extraEnvironment = mkOption {
        type = types.attrsOf types.str;
        default = {
          DJANGO_SETTINGS_MODULE = "endoreg_api.settings.central";
          CENTRAL_NODE = "true";
        };
        description = "Additional environment variables for the central service";
        example = {
          REDIS_URL = "redis://localhost:6379/0";
          CELERY_BROKER_URL = "redis://localhost:6379/1";
          CENTRAL_NODE = "true";
        };
      };
    };

    # Git Repository Options (same as local)
    repository = {
      url = mkOption {
        type = types.str;
        default = "https://github.com/wg-lux/endo-api";
        description = "Git repository URL for the Django API";
      };

      branch = mkOption {
        type = types.str;
        default = "environment-setup";
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
    # Enable required users and groups
    user.endoreg-service-user.enable = true;
    group.endoreg-service.enable = true;

    # Enable base roles
    roles = {
      desktop.enable = true;
      custom-packages.cuda = true;
      postgres.default.enable = true;  # Central node needs its own database
    };

    # Calculate combined allowed hosts (original + local nodes)
    services.luxnix.endoregDbApiLocal = {
      enable = true;
      
      # Pass configuration options to the service with central node modifications
      api = cfg.api // {
        # Extend allowed hosts with local nodes for central access
        djangoAllowedHosts = cfg.api.djangoAllowedHosts ++ cfg.localNodes;
        # Add central node identification
        extraSettings = {
          CENTRAL_NODES = cfg.centralNodes;
          LOCAL_NODES = cfg.localNodes;
          IS_CENTRAL_NODE = true;
        };
      };
      database = cfg.database;
      service = cfg.service;
      repository = cfg.repository;
    };

    # Create additional systemd tmpfiles for central configuration
    systemd.tmpfiles.rules = [
      # Central node sensitive data
      "d /mnt/endoreg-central-data 0770 root ${sensitiveServiceGroupName} -"
      # Central Django configuration directory
      "d /etc/endoreg-central-api 0755 root root -"
    ];

    # Generate Django secret key for central node if it doesn't exist
    systemd.services.endoreg-central-django-setup = {
      description = "Generate Django secret key and configuration for central node";
      wantedBy = [ "multi-user.target" ];
      before = [ "endo-api-boot.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        ExecStart = pkgs.writeShellScript "setup-central-django-config" ''
          set -euo pipefail
          
          # Generate Django secret key if it doesn't exist
          if [ ! -f ${cfg.api.djangoSecretKeyFile} ]; then
            echo "Generating Django secret key for central node..."
            mkdir -p $(dirname ${cfg.api.djangoSecretKeyFile})
            ${pkgs.openssl}/bin/openssl rand -base64 50 > ${cfg.api.djangoSecretKeyFile}
            chmod 640 ${cfg.api.djangoSecretKeyFile}
            chown root:${sensitiveServiceGroupName} ${cfg.api.djangoSecretKeyFile}
          fi
          
          # Ensure correct permissions
          chmod 640 ${cfg.api.djangoSecretKeyFile}
          chown root:${sensitiveServiceGroupName} ${cfg.api.djangoSecretKeyFile}
          
          # Create central nodes configuration file
          cat > /etc/endoreg-central-api/nodes.json << 'EOF'
          {
            "central_nodes": ${builtins.toJSON cfg.centralNodes},
            "local_nodes": ${builtins.toJSON cfg.localNodes},
            "is_central": true
          }
          EOF
          
          chmod 644 /etc/endoreg-central-api/nodes.json
          
          echo "Central Django configuration setup completed"
        '';
      };
    };

    # Open firewall for central API access
    networking.firewall = {
      allowedTCPPorts = [ cfg.api.port ];
    };

    # Configure nginx reverse proxy if HTTPS is enabled
    # REVISE, we use a central nginx to handle requests to the coloreg.de domain
    services.nginx = mkIf cfg.api.useHttps {
      enable = true;
      virtualHosts."${head cfg.api.djangoAllowedHosts}" = {
        enableACME = cfg.api.sslCertificatePath == null;
        forceSSL = true;
        sslCertificate = cfg.api.sslCertificatePath;
        sslCertificateKey = cfg.api.sslKeyPath;
        locations."/" = {
          proxyPass = "http://127.0.0.1:${toString cfg.api.port}";
          proxyWebsockets = true;
          extraConfig = ''
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
          '';
        };
      };
    };
  };
}
