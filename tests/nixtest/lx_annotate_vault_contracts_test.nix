{
  pkgs,
  ntlib,
  repoRoot,
  ...
}:
let
  vaultModule = "${repoRoot}/modules/nixos/luxnix/vault/default.nix";
  managedSecretsModule = "${repoRoot}/modules/nixos/roles/managed-secrets/default.nix";
  endoregClientModule = "${repoRoot}/modules/nixos/roles/endoreg-client/default.nix";
  clientUserModule = "${repoRoot}/modules/nixos/user/client/default.nix";
  lxAnnotateModuleRoot = "${repoRoot}/modules/nixos/services/lx-annotate-local";
  lxAnnotateConfig = pkgs.writeText "lx-annotate-config-and-subservices.nix" (
    builtins.concatStringsSep "\n" (
      map builtins.readFile (
        [ "${lxAnnotateModuleRoot}/config.nix" ]
        ++ pkgs.lib.filesystem.listFilesRecursive "${lxAnnotateModuleRoot}/subservices"
      )
    )
  );
  lxAnnotateEnv = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts/env.nix";
in
{
  suites."lx-annotate vault contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "vault-client-bootstrap-service-exists";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'services\.vault-auth-setup = mkIf vaultAuthEnabled' "vault auth bootstrap service must exist"
          assert_file_contains ${vaultModule} 'runtimeEnvironmentFile' "vault runtime env file must be defined"
          assert_file_contains ${vaultModule} 'method = mkOption' "vault auth method option must exist"
          assert_file_contains ${vaultModule} 'tokenFile' "vault tokenFile auth must exist"
          assert_file_contains ${vaultModule} 'roleIdFile' "vault approle roleId must exist"
          assert_file_contains ${vaultModule} 'secretIdFile' "vault approle secretId must exist"
        '';
      }
      {
        name = "vault-server-hub-pki-is-production-and-fail-closed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'storageBackend = "raft"' "Vault server must use integrated Raft storage"
          assert_file_contains ${vaultModule} 'luxnix-vault-bootstrap-hub-pki' "Vault must expose explicit hub PKI bootstrap tooling"
          assert_file_contains ${vaultModule} 'luxnix-vault-enroll-hub-site' "Vault must expose bounded per-site enrollment tooling"
          assert_file_contains ${vaultModule} 'client_flag=true' "hub certificates must be client identities"
          assert_file_contains ${vaultModule} 'server_flag=false' "hub client certificates must not be valid server identities"
          assert_file_contains ${vaultModule} 'services\.luxnix-vault-issue-hub-client-certificate = lib\.mkIf clientHubPkiCfg\.enable' "site client identities must be issued and renewed by a dedicated service"
          assert_file_contains ${vaultModule} 'Vault returned a client certificate and private key that do not match' "issued certificate and key pairs must be verified"
          assert_file_contains ${vaultModule} 'source-node-secret' "site enrollment must provision separate request-authentication material"
          assert_file_contains ${vaultModule} 'luxnix-vault-install-hub-site-enrollment' "site enrollment bundles must have a bounded installer"
          assert_file_contains ${vaultModule} 'AppRole hub-site enrollment files and the recipient public key must share the node-secret directory' "site enrollment paths must preserve one protected directory boundary"
          assert_file_contains ${vaultModule} 'vault-server-ca.pem' "site enrollment must include pinned Vault server trust material"
          assert_file_contains ${vaultModule} 'kv_mount/data/nodes' "site AppRoles must read only their own request-authentication secret"
          assert_file_contains ${vaultModule} 'lx_hub_source_node_secret' "site request-authentication material must be refreshed through managed secrets"
          assert_file_contains ${vaultModule} 'services\.luxnix-vault-publish-hub-client-ca = lib\.mkIf hubPkiCfg\.enable' "hub client CA publication must be managed"
          assert_file_contains ${vaultModule} '--cacert.*serverCfg\.caCertFile' "hub CA publication must verify a private Vault server certificate"
          assert_file_contains ${vaultModule} '--retry-connrefused' "hub CA publication must tolerate the bounded Vault listener startup race"
          assert_file_contains ${vaultModule} 'Restart = "on-failure"' "hub CA publication must retry a failed refresh"
          assert_file_contains ${vaultModule} 'openssl x509.*-checkend' "published CA material must be validated"
          assert_file_contains ${vaultModule} 'VAULT_TOKEN are required' "PKI bootstrap must require an explicit administrative token"
        '';
      }
      {
        name = "hub-envelope-keys-are-role-separated-and-fail-closed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'lx_hub_recipient_public_key' "sites must receive the hub envelope public key through managed secrets"
          assert_file_contains ${vaultModule} 'kv_mount/data/.*recipient_public_key_kv_path' "site AppRoles may read the dedicated hub recipient public-key path"
          assert_file_contains ${vaultModule} 'vault kv put.*public_key=-' "PKI bootstrap must publish only the hub recipient public key"
          assert_file_contains ${vaultModule} 'LUXNIX_VAULT_ALLOW_HUB_RECIPIENT_ROTATION' "recipient public-key replacement must require an explicit rotation action"
          assert_file_contains ${vaultModule} 'openssl pkey -pubin' "published and fetched recipient keys must be parsed as public keys"
          assert_file_contains ${vaultModule} 'grep -q X25519' "published and fetched recipient keys must be restricted to X25519"
          assert_file_contains ${lxAnnotateConfig} 'lx-annotate-hub-envelope-key-preflight' "hub sender and receiver services must be gated on envelope-key validation"
          assert_file_contains ${lxAnnotateConfig} 'builtins.length cfg\.hub\.transferApi\.recipientPrivateKeyFiles <= 3' "recipient rotation must permit only a bounded current-and-retiring key set"
          assert_file_contains ${lxAnnotateEnv} 'LX_ANNOTATE_HUB_EXPORT_RECIPIENT_PUBLIC_KEY_FILE' "site workers must receive only the hub recipient public-key path"
          assert_file_contains ${lxAnnotateEnv} 'ENDOREG_HUB_TRANSFER_RECIPIENT_PRIVATE_KEY_FILES' "the hub receiver must receive its explicit private-key path list"
          if grep -Eq 'vault kv put.*private_key' ${vaultModule}; then
            echo "the hub recipient private key must never be published to Vault KV" >&2
            exit 1
          fi
        '';
      }
      {
        name = "lx-annotate-network-nodes-are-provisioned-at-the-model-boundary";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'NetworkNode\.objects\.update_or_create' "NetworkNode records must be provisioned idempotently"
          assert_file_contains ${lxAnnotateConfig} 'node\.set_shared_secret' "NetworkNode request secrets must be hashed through the model helper"
          assert_file_contains ${lxAnnotateConfig} 'transaction\.atomic' "NetworkNode provisioning must be atomic"
          assert_file_contains ${lxAnnotateConfig} 'hub\.node_provisioned' "NetworkNode provisioning must emit structured JSON events"
          assert_file_contains ${lxAnnotateConfig} 'lx-annotate-hub-node-provisioning' "application services must be gated on NetworkNode provisioning"
          assert_file_contains ${lxAnnotateConfig} '/api/media/hub/transfers/' "machine-to-machine hub routes must bypass browser OIDC redirects"
          assert_file_contains ${lxAnnotateConfig} 'cfg\.hub\.transferApi\.enable' "the OIDC route policy must be scoped to transfer API hubs"
          assert_file_contains ${lxAnnotateConfig} 'lx_annotate\.settings\.settings_prod' "hub OIDC policy initialization must preserve the lx-annotate settings boundary"
          assert_file_contains ${lxAnnotateConfig} 'file=sys\.stderr' "hub OIDC policy logging must not corrupt command stdout contracts"
          assert_file_contains ${lxAnnotateEnv} 'DJANGO_ALLOWED_HOSTS = envAllowedHosts' "production deployments must export Django's required allowed-hosts variable"
          assert_file_contains ${lxAnnotateConfig} 'install --force-reinstall --no-deps.*staged_wheel_path' "changed wheel content must replace an installed wheel with the same version"
        '';
      }
      {
        name = "lx-annotate-wheel-runtime-is-owned-by-the-service-principal";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'd .*runtimeWheelRootPath.* 0750 .*endoreg-service-user-name' "wheel runtime root must be created for the service principal"
          assert_file_contains ${lxAnnotateConfig} 'z .*runtimeWheelRootPath.* 0750 .*endoreg-service-user-name' "existing wheel runtime ownership must be corrected"
        '';
      }
      {
        name = "managed-secrets-handles-custom-secrets-atomically";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${managedSecretsModule} 'allManagedSecrets = .*activeBuiltinSecrets // activeCustomSecrets' "custom secrets must be included in generation set"
          assert_file_contains ${managedSecretsModule} 'refreshOnBoot = mkOption' "refreshOnBoot option must exist"
          assert_file_contains ${managedSecretsModule} 'mktemp "\$SECRET_DIR/\..*\.tmp\.' "secret refresh must use temp files"
          assert_file_contains ${managedSecretsModule} 'mv -f "\$TARGET_FILE" "\$SECRET_FILE"' "secret writes must be atomic"
          assert_file_contains ${managedSecretsModule} 'vault-auth-setup\.service' "managed-secrets must wait for vault auth bootstrap"
        '';
      }
      {
        name = "endoreg-clients-can-start-with-cached-secrets-while-vault-is-offline";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${endoregClientModule} 'vault\.client\.allowOffline = mkDefault true' "EndoReg clients must opt into offline Vault startup"
          assert_file_contains ${vaultModule} 'continuing with locally cached secrets' "Vault auth failures must degrade to cached secrets for offline-capable clients"
          assert_file_contains ${vaultModule} 'continuing with cached hub PKI files' "hub certificate renewal must reuse cached PKI files while Vault is offline"
          assert_file_contains ${vaultModule} 'VAULT_CLIENT_TIMEOUT=5s' "offline Vault authentication must use a bounded timeout"
          assert_file_contains ${managedSecretsModule} 'continuing with the existing local secret' "failed Vault refreshes must preserve existing secrets"
          assert_file_contains ${managedSecretsModule} '\[ -f "\$SECRET_FILE" \]' "offline fallback must require an existing secret file"
          assert_file_contains ${managedSecretsModule} 'VAULT_CLIENT_TIMEOUT=5s' "offline Vault secret refresh must use a bounded timeout"
        '';
      }
      {
        name = "managed-secrets-does-not-own-human-facing-passwords";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${managedSecretsModule} 'humanFacingSecretNames' "managed-secrets must classify human-facing password built-ins"
          assert_file_contains ${managedSecretsModule} 'humanFacing = mkOption' "custom secrets must be able to declare human-facing credentials"
          assert_file_contains ${managedSecretsModule} 'allowGeneratedHumanSecrets' "human-facing generated secrets must require an explicit migration override"
          assert_file_contains ${managedSecretsModule} 'client_user_password_hash' "client user password hash must be treated as human-facing"
          assert_file_contains ${managedSecretsModule} 'managedSecretsSopsPathConflicts' "managed-secrets must refuse SOPS path ownership conflicts"
          assert_file_contains ${clientUserModule} 'luxnixValidateClientPasswordFile' "client user password hash files must be validated before activation"
        '';
      }
      {
        name = "lx-annotate-vault-secrets-are-root-only-and-refreshed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'lx_annotate_luks_key' "LUKS key secret must be declared"
          assert_file_contains ${lxAnnotateConfig} 'lx_annotate_luks_uuid' "LUKS UUID secret must be declared"
          assert_file_contains ${lxAnnotateConfig} 'lx_annotate_master_key' "application master key secret must be declared"
          assert_file_contains ${lxAnnotateConfig} 'permissions = "400"' "lx-annotate Vault secrets must be root-only"
          assert_file_contains ${lxAnnotateConfig} 'refreshOnBoot = true' "lx-annotate Vault secrets must refresh on boot"
        '';
      }
      {
        name = "lx-annotate-vault-mode-fails-closed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'networking\.hostName to be set' "vault mode must require hostname"
          assert_file_contains ${lxAnnotateConfig} 'requires luxnix\.vault client configuration' "vault mode must require explicit vault client config"
          assert_file_contains ${lxAnnotateConfig} 'setupService' "lx-annotate must order after managed secrets setup"
          assert_file_contains ${lxAnnotateConfig} 'lx-annotate-master-key-check' "lx-annotate must validate the application master key before boot"
          assert_file_contains ${lxAnnotateConfig} 'lx-annotate-master-key-check.service' "lx-annotate boot must require the master key guard"
        '';
      }
    ];
  };
}
