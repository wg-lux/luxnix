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

    paths = {
      storageBaseDir = mkOption {
        type = types.path;
        default = "/var/lib/endoreg-client";
        description = "Base directory for endoreg client storage and input directories.";
      };

      videoInputDir = mkOption {
        type = types.path;
        default = "${config.roles.endoreg-client.paths.storageBaseDir}/video_input";
        description = "Directory watched for incoming video files.";
      };

      pdfInputDir = mkOption {
        type = types.path;
        default = "${config.roles.endoreg-client.paths.storageBaseDir}/pdf_input";
        description = "Directory watched for incoming PDF files.";
      };

      desktopDirName = mkOption {
        type = types.str;
        default = "Desktop";
        example = "Schreibtisch";
        description = "Desktop directory name for the client user (localization support).";
      };
    };

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

    defaultCenter = mkOption {
      type = types.str;
      default = "university_hospital_wuerzburg";
      description = "Default center value for endoreg client";
      example = "university_hospital_wuerzburg";
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
        default = [ "localhost" "127.0.0.1"];
        description = "Django ALLOWED_HOSTS setting";
        example = [ "lx-annotate.endo-reg.net" "localhost" "127.0.0.1" ];
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
        example = [ "lx-annotate.endo-reg.net" "http://localhost:3000" ];
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

      settingsProfile = mkOption {
        type = types.enum [ "dev" "prod" "central" "test" ];
        default = "prod";
        description = "Base settings profile to derive Django settings module.";
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

      #TODO unify data and storage dir
      dataDir = mkOption {
        type = types.str;
        default = "data";
        description = "Relative path to the data directory inside the repository.";
      };

      storageDir = mkOption {
        type = types.str;
        default = "data/storage";
        description = "Relative or absolute path used for STORAGE_DIR.";
      };

      confDir = mkOption {
        type = types.str;
        default = "conf";
        description = "Relative path to configuration directory inside the repository.";
      };

      confTemplateDir = mkOption {
        type = types.str;
        default = "conf_template";
        description = "Relative path to configuration template directory.";
      };

      djangoModule = mkOption {
        type = types.str;
        default = "endo_api";
        description = "Python module containing the Django project.";
      };

      assetDir = mkOption {
        type = types.str;
        default = "tests/assets";
        description = "Relative or absolute path for ASSET_DIR.";
      };

      httpProtocol = mkOption {
        type = types.enum [ "http" "https" ];
        default = "http";
        description = "Explicit HTTP protocol to advertise in BASE_URL.";
      };

      baseUrl = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Explicit BASE_URL; constructed from protocol/host/port when null.";
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
        description = "Whether to enable RUN_VIDEO_TESTS environment flag.";
      };

      skipExpensiveTests = mkOption {
        type = types.bool;
        default = true;
        description = "Whether to enable SKIP_EXPENSIVE_TESTS environment flag.";
      };

      extraSettings = mkOption {
        type = types.attrsOf types.anything;
        default = {};
        description = "Additional attributes exported into Django local settings.";
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

    environmentDefaults = {
      hfHome = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Default HuggingFace home directory. When null, derived from the service user home.";
      };

      hfHubCache = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Default HuggingFace hub cache directory. When null, derived from the service user home.";
      };

      transformersCache = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Default transformers cache directory. When null, derived from the service user home.";
      };

      hfHubEnableTransfer = mkOption {
        type = types.bool;
        default = true;
        description = "Whether to enable HF_HUB_ENABLE_HF_TRANSFER by default.";
      };

      ollamaModelsDir = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Default Ollama models directory. When null, derived from the service user home.";
      };

      ollamaKeepAlive = mkOption {
        type = types.str;
        default = "4h";
        description = "Default keep-alive duration for Ollama.";
      };
    };

    lxAnnotate = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Enable the lx-annotate-local service on endoreg clients.";
      };

      debug = mkOption {
        type = types.submodule {
          options = {
            enable = mkOption {
              type = types.bool;
              default = false;
              description = "Enable verbose debug output for the lx-annotate-local service.";
            };
          };
        };
        default = {};
        description = "Debug configuration for lx-annotate-local.";
      };

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
        default = {};
        description = "Repository configuration for lx-annotate.";
      };

      django = mkOption {
        type = types.submodule {
          options = {
            djangoModule = mkOption {
              type = types.str;
              default = "lx_annotate";
              description = "Python module containing the lx-annotate Django project.";
            };

            dataDir = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Override for the lx-annotate data directory. Uses the shared API value when null.";
            };

            storageDir = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Override for the lx-annotate storage directory. Uses the shared API value when null.";
            };

            confDir = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Override for the lx-annotate configuration directory. Uses the shared API value when null.";
            };

            confTemplateDir = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Override for the lx-annotate configuration template directory. Uses the shared API value when null.";
            };

            assetDir = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Override for the lx-annotate asset directory. Uses the shared API value when null.";
            };
          };
        };
        default = {};
        description = "Overrides for lx-annotate Django-specific paths.";
      };

      runtime = mkOption {
        type = types.submodule {
          options = {
            limits = mkOption {
              type = types.submodule {
                options = {
                  memoryMax = mkOption {
                    type = types.str;
                    default = "8G";
                    description = "MemoryMax limit applied to the lx-annotate-local service.";
                  };

                  cpuQuota = mkOption {
                    type = types.str;
                    default = "800%";
                    description = "CPUQuota assigned to the lx-annotate-local service.";
                  };
                };
              };
              default = {};
              description = "Resource limit configuration for lx-annotate-local.";
            };

            environment = mkOption {
              type = types.submodule {
                options = {
                  hfHome = mkOption {
                    type = types.nullOr types.str;
                    default = null;
                    description = "Override HuggingFace home directory for lx-annotate.";
                  };

                  hfHubCache = mkOption {
                    type = types.nullOr types.str;
                    default = null;
                    description = "Override HuggingFace hub cache directory for lx-annotate.";
                  };

                  transformersCache = mkOption {
                    type = types.nullOr types.str;
                    default = null;
                    description = "Override transformers cache directory for lx-annotate.";
                  };

                  hfHubEnableTransfer = mkOption {
                    type = types.nullOr types.bool;
                    default = null;
                    description = "Override HF_HUB_ENABLE_HF_TRANSFER for lx-annotate.";
                  };

                  ollamaModelsDir = mkOption {
                    type = types.nullOr types.str;
                    default = null;
                    description = "Override Ollama models directory for lx-annotate.";
                  };

                  ollamaKeepAlive = mkOption {
                    type = types.nullOr types.str;
                    default = null;
                    description = "Override Ollama keep-alive duration for lx-annotate.";
                  };
                };
              };
              default = {};
              description = "Environment variable overrides for lx-annotate-local.";
            };
          };
        };
        default = {};
        description = "Runtime configuration for lx-annotate-local.";
      };
    };
  };

  config = mkIf cfg.enable (let
    clientUserName =
      if config ? user && config.user ? client && config.user.client ? name
      then config.user.client.name
      else "client-user";
    clientUserHome =
      let
        maybeHome = if config ? user && config.user ? client && config.user.client ? home then config.user.client.home else null;
      in
        if maybeHome != null then maybeHome else "/home/${clientUserName}";
    clientHomeStateVersion =
      if config ? user && config.user ? client && config.user.client ? homeStateVersion
      then config.user.client.homeStateVersion
      else (config.system.stateVersion or "24.05");
    storageBaseDir = cfg.paths.storageBaseDir;
    videoInputDir = cfg.paths.videoInputDir;
    pdfInputDir = cfg.paths.pdfInputDir;

    firstNonNull = values: lib.foldl' (acc: val: if acc != null then acc else val) null values;

    endoregServiceUserName =
      if config ? user && config.user ? endoreg-service-user && config.user.endoreg-service-user ? name
      then config.user.endoreg-service-user.name
      else "endoreg-service-user";
    endoregServiceUserHome =
      let
        maybeHome = if config ? user && config.user ? endoreg-service-user && config.user.endoreg-service-user ? home
          then config.user.endoreg-service-user.home
          else null;
      in
      if maybeHome != null then maybeHome else "/var/${endoregServiceUserName}";

    envDefaultsCfg = cfg.environmentDefaults;
    envOverrides = cfg.lxAnnotate.runtime.environment;

    defaultHfHome = "${endoregServiceUserHome}/.cache/huggingface";
    defaultHfHubCache = "${endoregServiceUserHome}/.cache/huggingface/hub";
    defaultTransformersCache = defaultHfHubCache;
    defaultOllamaModelsDir = "${endoregServiceUserHome}/.ollama/models";

    resolvedHfHome = firstNonNull [ envOverrides.hfHome envDefaultsCfg.hfHome defaultHfHome ];
    resolvedHfHubCache = firstNonNull [ envOverrides.hfHubCache envDefaultsCfg.hfHubCache defaultHfHubCache ];
    resolvedTransformersCache = firstNonNull [ envOverrides.transformersCache envDefaultsCfg.transformersCache defaultTransformersCache ];
    resolvedOllamaModelsDir = firstNonNull [ envOverrides.ollamaModelsDir envDefaultsCfg.ollamaModelsDir defaultOllamaModelsDir ];
    resolvedOllamaKeepAlive = firstNonNull [ envOverrides.ollamaKeepAlive envDefaultsCfg.ollamaKeepAlive ];
    resolvedHfHubEnableTransfer =
      let specific = envOverrides.hfHubEnableTransfer;
      in if specific != null then specific else envDefaultsCfg.hfHubEnableTransfer;

    annotateEnvironment = {
      hfHome = resolvedHfHome;
      hfHubCache = resolvedHfHubCache;
      transformersCache = resolvedTransformersCache;
      hfHubEnableTransfer = resolvedHfHubEnableTransfer;
      ollamaModelsDir = resolvedOllamaModelsDir;
      ollamaKeepAlive = resolvedOllamaKeepAlive;
    };

    annotateRuntimeLimits = cfg.lxAnnotate.runtime.limits;

    annotateDjangoOverrides = {
      djangoModule = cfg.lxAnnotate.django.djangoModule;
      dataDir = if cfg.lxAnnotate.django.dataDir != null then cfg.lxAnnotate.django.dataDir else cfg.api.dataDir;
      storageDir = if cfg.lxAnnotate.django.storageDir != null then cfg.lxAnnotate.django.storageDir else cfg.api.storageDir;
      confDir = if cfg.lxAnnotate.django.confDir != null then cfg.lxAnnotate.django.confDir else cfg.api.confDir;
      confTemplateDir = if cfg.lxAnnotate.django.confTemplateDir != null then cfg.lxAnnotate.django.confTemplateDir else cfg.api.confTemplateDir;
      assetDir = if cfg.lxAnnotate.django.assetDir != null then cfg.lxAnnotate.django.assetDir else cfg.api.assetDir;
    };

    annotateExtraSettings =
      let
        baseExtraSettings = cfg.api.extraSettings;
      in
      recursiveUpdate baseExtraSettings {
        CENTRAL_NODES = cfg.centralNodes;
        IS_CENTRAL_NODE = false;
      };

    annotateDjango = recursiveUpdate cfg.api (annotateDjangoOverrides // {
      extraSettings = annotateExtraSettings;
    });
  in {
    user.client.enable = mkDefault true;
    user.endoreg-service-user.enable = true;
    group.endoreg-service.enable = true;  # Ensure the group is created
    group.endoreg-service.members = mkAfter [ clientUserName ];

    roles = {
      desktop.enable = true;
      custom-packages.cuda = true;
      aglnet.client.enable = true;
      managed-secrets.enable = mkDefault true;
    };

    luxnix.nvidia-prime.enable = true;

    services.luxnix.endoregDbApiLocal = mkIf (!config.roles.endoreg-db-central-01.enable) {
      enable = mkDefault cfg.dbApiLocal;
      
      # Pass configuration options to the service
      api = cfg.api // {
        # Add central nodes information
        extraSettings = recursiveUpdate cfg.api.extraSettings {
          CENTRAL_NODES = cfg.centralNodes;
          IS_CENTRAL_NODE = false;
        };
      };
      database = cfg.database;
      service = cfg.service;
      repository = cfg.repository;
    };

    services.luxnix.fileMover.enable = true;

    services.luxnix.lxAnnotateLocal = {
      enable = mkDefault cfg.lxAnnotate.enable;
      debug.enable = cfg.lxAnnotate.debug.enable;
      source = cfg.lxAnnotate.source;
      django = annotateDjango;
      database = cfg.database;
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
    ] ++ [
      "d ${storageBaseDir} 0770 root endoreg-service -"
      "d ${videoInputDir} 0770 root endoreg-service -"
      "d ${pdfInputDir} 0770 root endoreg-service -"
    ];

    home-manager.users.${clientUserName} = { config, ... }: let
      outOfStore = config.lib.file.mkOutOfStoreSymlink;
    in {
      home.username = mkDefault clientUserName;
      home.homeDirectory = mkDefault clientUserHome;
      home.stateVersion = mkDefault clientHomeStateVersion;

      roles.desktop.enable = mkDefault true;

      home.file."${cfg.paths.desktopDirName}/Video Input" = {
        source = outOfStore videoInputDir;
        force = true;
      };
      home.file."${cfg.paths.desktopDirName}/PDF Input" = {
        source = outOfStore pdfInputDir;
        force = true;
      };
    };

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
  });
}
