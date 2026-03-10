{ lib }:
let
  inherit (lib) mkOption optionalAttrs types;
in
{
  defaults ? { },
  includeKeycloak ? false,
  logLevelType ? types.str,
  httpProtocolType ? types.enum [
    "http"
    "https"
  ],
}:
{
  hostname = mkOption {
    type = types.str;
    default = defaults.hostname or "localhost";
    description = "Hostname for the Django service.";
  };

  port = mkOption {
    type = types.port;
    default = defaults.port or 8000;
    description = "Port for the Django service.";
  };

  useHttps = mkOption {
    type = types.bool;
    default = defaults.useHttps or false;
    description = "Whether HTTPS should be used for public URLs.";
  };

  sslCertificatePath = mkOption {
    type = types.nullOr types.path;
    default = defaults.sslCertificatePath or null;
    description = "Path to SSL certificate file.";
  };

  sslKeyPath = mkOption {
    type = types.nullOr types.path;
    default = defaults.sslKeyPath or null;
    description = "Path to SSL private key file.";
  };

  djangoAllowedHosts = mkOption {
    type = types.listOf types.str;
    default =
      defaults.djangoAllowedHosts
      or [
        "localhost"
        "127.0.0.1"
      ];
    description = "Django ALLOWED_HOSTS setting.";
  };

  corsAllowedOrigins = mkOption {
    type = types.listOf types.str;
    default = defaults.corsAllowedOrigins or [ ];
    description = "CORS allowed origins.";
  };

  djangoDebug = mkOption {
    type = types.bool;
    default = defaults.djangoDebug or false;
    description = "Enable Django DEBUG mode.";
  };

  djangoSecretKeyFile = mkOption {
    type = types.path;
    default = defaults.djangoSecretKeyFile or "/etc/secrets/vault/django_secret_key";
    description = "Path to file containing Django SECRET_KEY.";
  };

  logLevel = mkOption {
    type = logLevelType;
    default = defaults.logLevel or "INFO";
    description = "Django logging level.";
  };

  maxRequestSize = mkOption {
    type = types.str;
    default = defaults.maxRequestSize or "100M";
    description = "Maximum request size for file uploads.";
  };

  timeZone = mkOption {
    type = types.str;
    default = defaults.timeZone or "UTC";
    description = "Django timezone setting.";
  };

  language = mkOption {
    type = types.str;
    default = defaults.language or "en-us";
    description = "Django language setting.";
  };

  settingsProfile = mkOption {
    type = types.enum [
      "dev"
      "prod"
      "central"
      "test"
    ];
    default = defaults.settingsProfile or "prod";
    description = "Base settings profile to derive Django settings module.";
  };

  settingsModule = mkOption {
    type = types.nullOr types.str;
    default = defaults.settingsModule or null;
    description = "Explicit Django settings module (overrides settingsProfile).";
  };

  djangoEnv = mkOption {
    type = types.nullOr types.str;
    default = defaults.djangoEnv or null;
    description = "Value for DJANGO_ENV; inferred from settingsProfile when null.";
  };

  dataDir = mkOption {
    type = types.str;
    default = defaults.dataDir or "data";
    description = "Relative path to data directory inside the repository.";
  };

  confDir = mkOption {
    type = types.str;
    default = defaults.confDir or "conf";
    description = "Relative path to configuration directory inside the repository.";
  };

  confTemplateDir = mkOption {
    type = types.str;
    default = defaults.confTemplateDir or "conf_template";
    description = "Relative path to configuration template directory inside the repository.";
  };

  djangoModule = mkOption {
    type = types.str;
    default = defaults.djangoModule or "endo_api";
    description = "Python module containing the Django project.";
  };

  assetDir = mkOption {
    type = types.str;
    default = defaults.assetDir or "tests/assets";
    description = "Relative or absolute path used as ASSET_DIR.";
  };

  httpProtocol = mkOption {
    type = httpProtocolType;
    default = defaults.httpProtocol or "https";
    description = "HTTP protocol to use when constructing BASE_URL.";
  };

  baseUrl = mkOption {
    type = types.nullOr types.str;
    default = defaults.baseUrl or null;
    description = "Explicit BASE_URL; constructed from protocol/host/port when null.";
  };

  staticUrl = mkOption {
    type = types.str;
    default = "/";
    description = "STATIC_URL value exported to the application.";
  };

  mediaUrl = mkOption {
    type = types.str;
    default = defaults.mediaUrl or "/media/";
    description = "MEDIA_URL value exported to the application.";
  };

  runVideoTests = mkOption {
    type = types.bool;
    default = defaults.runVideoTests or false;
    description = "Whether RUN_VIDEO_TESTS should be enabled.";
  };

  skipExpensiveTests = mkOption {
    type = types.bool;
    default = defaults.skipExpensiveTests or true;
    description = "Whether SKIP_EXPENSIVE_TESTS should be enabled.";
  };

  extraSettings = mkOption {
    type = types.attrsOf types.anything;
    default = defaults.extraSettings or { };
    description = "Additional settings to pass to Django configuration.";
  };
}
// optionalAttrs includeKeycloak {
  keycloakSecretFile = mkOption {
    type = types.path;
    default = defaults.keycloakSecretFile or "/etc/secrets/vault/keycloak.env";
    description = "Path to file containing the Keycloak client secret.";
  };

  keycloakClientId = mkOption {
    type = types.str;
    default = defaults.keycloakClientId or "endoregdb-api";
    description = "Keycloak client ID.";
  };
}
