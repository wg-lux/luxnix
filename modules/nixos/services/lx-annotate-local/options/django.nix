{ lib, lxAnnotateRuntime, ... }:
let
  inherit (lib) mkOption types;
  inherit (lxAnnotateRuntime.helpers) mkDjangoOptions;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    django = mkOption {
      type = types.submodule {
        options =
          (mkDjangoOptions {
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
          })
          // {
            sslCaCertificatePath = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "CA bundle for verified local HTTPS acceptance; null trusts the generated self-signed certificate.";
            };
            enrollLegacyDefaultSalt = mkOption {
              type = types.bool;
              default = true;
              description = ''
                Automatically provision and recover a per-machine active identity
                salt, retaining default_salt for legacy reads. Existing managed
                salts are preserved with two root-owned recovery copies. External
                salt configurations must explicitly disable managed provisioning.
                Requires keyring-capable writers; never replaces an established salt.
              '';
            };
            identitySaltFile = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Private file holding an established non-default identity salt, exported as DJANGO_SALT_FILE.";
            };
            centerIdentitySalt = mkOption {
              type = types.bool;
              default = false;
              description = ''
                Enroll from the Vault identity salt scoped to endoreg-client.defaultCenterKey.
                Set through host_services or group_services in inventory. Requires the
                center-scoped Vault enrollment policy. Existing different salts fail closed
                and require verified migration; they are never overwritten by enrollment.
                Enable through inventory after enrollment and legacy migration review.
              '';
            };
            identitySaltKeyringFile = mkOption {
              type = types.nullOr types.str;
              default = null;
              description = "Private identity manifest exported as DJANGO_IDENTITY_SALT_KEYRING_FILE; takes precedence over a single salt file.";
            };
            automaticIdentitySaltMigration = mkOption {
              type = types.bool;
              default = true;
              description = "Periodically migrate verified identities to the configured keyring's active salt in the background, retaining blocked identities and retiring salts.";
            };
            identitySaltMigrationReviewFile = mkOption {
              type = types.nullOr (types.strMatching "/.*");
              default = null;
              description = "Absolute path to a private, service-readable reviewed identity YAML file; contents must never enter the Nix store. Passed to rotate_identity_salt --review-file.";
            };
          };
      };
      default = { };
      description = "Django configuration options for lx-annotate.";
    };
  };
}
