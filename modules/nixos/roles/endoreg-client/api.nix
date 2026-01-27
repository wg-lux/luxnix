{ lib }:
with lib;
{
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
    default = [
      "localhost"
      "127.0.0.1"
    ];
    description = "Django ALLOWED_HOSTS setting";
    example = [
      "lx-annotate.local"
      "localhost"
      "127.0.0.1"
    ];
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
    default = [
      "lx-annotate.local"
      "https://lx-annotate.local"
      "http://localhost:3000"
    ];
    description = "CORS allowed origins for the API";
    example = [
      "lx-annotate.local"
      "https://lx-annotate.local"
      "http://localhost:3000"
    ];
  };

  logLevel = mkOption {
    type = types.enum [
      "DEBUG"
      "INFO"
      "WARNING"
      "ERROR"
      "CRITICAL"
    ];
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
    type = types.enum [
      "dev"
      "prod"
      "central"
      "test"
    ];
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

  dataDir = mkOption {
    type = types.str;
    default = "data";
    description = "Relative path to the data directory inside the repository.";
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
    type = types.enum [
      "http"
      "https"
    ];
    default = "https";
    description = "Explicit HTTP protocol to advertise in BASE_URL.";
  };

  baseUrl = mkOption {
    type = types.nullOr types.str;
    default = null;
    description = "Explicit BASE_URL; constructed from protocol/host/port when null.";
  };

  staticUrl = mkOption {
    type = types.str;
    default = "static";
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
    default = { };
    description = "Additional attributes exported into Django local settings.";
  };
}
