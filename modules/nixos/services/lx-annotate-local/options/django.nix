{ lib, lxAnnotateRuntime, ... }:
let
  inherit (lib) mkOption types;
  inherit (lxAnnotateRuntime.helpers) mkDjangoOptions;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    django = mkOption {
      type = types.submodule {
        options = (mkDjangoOptions {
          defaults = {
            hostname = "lx-annotate.local";
            port = 8117;
            useHttps = true;
            sslCertificatePath = null;
            sslKeyPath = null;
            djangoAllowedHosts = [
              "lx-annotate.local"
              "127.0.0.1"
            ];
            corsAllowedOrigins = [
              "https://lx-annotate.local"
              "http://127.0.0.1"
            ];
            djangoDebug = false;
            djangoSecretKeyFile = "/etc/secrets/vault/django_secret_key";
            keycloakSecretFile = "/etc/secrets/vault/keycloak.env";
            keycloakClientId = "endoregdb-api";
            logLevel = "INFO";
            maxRequestSize = "100M";
            timeZone = "Europe/Berlin";
            language = "en-us";
            settingsProfile = "prod";
            settingsModule = null;
            djangoEnv = null;
            dataDir = "data";
            confDir = "conf";
            djangoModule = "lx_annotate";
            assetDir = "tests/assets";
            httpProtocol = "https";
            baseUrl = "https://lx-annotate.local";
            staticUrl = "/static/";
            mediaUrl = "/media/";
            runVideoTests = false;
            skipExpensiveTests = true;
            extraSettings = { };
          };
          includeKeycloak = true;
          logLevelType = types.str;
          httpProtocolType = types.str;
        }) // {
          enrollLegacyDefaultSalt = mkOption {
            type = types.bool;
            default = false;
            description = ''
              Explicitly enroll historical default_salt as a retiring identity
              generation and provision one new active salt. Requires coordinated
              keyring-capable identity writers. This does not run bulk migration
              or rotate media or Django signing keys. Never enable on a host
              whose established identity salt is unknown or different.
            '';
          };
          identitySaltFile = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Private file holding an established non-default identity salt, exported as DJANGO_SALT_FILE.";
          };
          identitySaltKeyringFile = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Private identity manifest exported as DJANGO_IDENTITY_SALT_KEYRING_FILE; takes precedence over a single salt file.";
          };
        };
      };
      default = { };
      description = "Django configuration options for lx-annotate.";
    };
  };
}
