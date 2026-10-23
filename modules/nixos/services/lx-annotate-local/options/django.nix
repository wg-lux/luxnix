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
                Recover established machine identity salts or enroll an authoritative
                center bundle, retaining historical salts for source matching. Existing managed
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
                Opt-in shared pseudonymization salt for all machines of one center. Enrolls
                from the Vault salt scoped to endoreg-client.defaultCenterKey, which the Vault
                host publishes only when that center is listed in
                luxnix.vault.server.hubPki.sharedIdentityCenters. Existing differing local
                salts fail closed and are retained as historical keys; they are never overwritten.
                Enable per center through inventory after reviewing legacy hash links.
              '';
            };
            identitySaltViaSecretSpec = mkOption {
              type = types.bool;
              default = false;
              description = "Retired central salt injection; enabling this option fails evaluation.";
            };
            identitySaltGeneration = mkOption {
              type = types.nullOr types.ints.positive;
              default = null;
              description = "Reviewed center generation required for file-free SecretSpec delivery.";
            };
            identitySaltFingerprint = mkOption {
              type = types.str;
              default = "";
              description = "Reviewed SHA-256 fingerprint of the active UTF-8 salt; public admission pin, never the salt itself.";
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
