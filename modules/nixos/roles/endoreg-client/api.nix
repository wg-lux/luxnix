{ lib }:
let
  mkDjangoOptions = import ../../lib/django-options.nix { inherit lib; };
in
mkDjangoOptions {
  defaults = {
    hostname = "localhost";
    port = 8118;
    useHttps = false;
    sslCertificatePath = null;
    sslKeyPath = null;
    djangoAllowedHosts = [
      "localhost"
      "127.0.0.1"
    ];
    djangoDebug = false;
    djangoSecretKeyFile = "/etc/secrets/vault/django_secret_key";
    corsAllowedOrigins = [
      "lx-annotate.local"
      "https://lx-annotate.local"
      "http://localhost:3000"
    ];
    logLevel = "INFO";
    maxRequestSize = "100M";
    timeZone = "UTC";
    language = "en-us";
    settingsProfile = "prod";
    settingsModule = null;
    djangoEnv = null;
    dataDir = "data";
    confDir = "conf";
    confTemplateDir = "conf_template";
    djangoModule = "endo_api";
    assetDir = "tests/assets";
    httpProtocol = "https";
    baseUrl = null;
    staticUrl = "static";
    mediaUrl = "/media/";
    runVideoTests = false;
    skipExpensiveTests = true;
    extraSettings = { };
  };

  logLevelType = lib.types.enum [
    "DEBUG"
    "INFO"
    "WARNING"
    "ERROR"
    "CRITICAL"
  ];

  httpProtocolType = lib.types.enum [
    "http"
    "https"
  ];
}
