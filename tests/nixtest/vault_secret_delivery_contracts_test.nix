{
  pkgs,
  ntlib,
  repoRoot,
  ...
}: let
  vaultModule = "${repoRoot}/modules/nixos/luxnix/vault/default.nix";
  managedSecretsModule = "${repoRoot}/modules/nixos/roles/managed-secrets/default.nix";
  localUsersModule = "${repoRoot}/modules/nixos/security/local-users/default.nix";
  lxAnnotateConfig = "${repoRoot}/modules/nixos/services/lx-annotate-local/config.nix";
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
  lxAnnotateEnvScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts/env.nix";
in {
  suites."vault secret delivery contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "vault-runtime-files-are-root-only-and-ephemeral";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'runtimeDir = "/run/luxnix/vault"' "vault runtime directory path must stay fixed and explicit"
          assert_file_contains ${vaultModule} 'chmod 0600 "\$TMP_TOKEN"' "temporary Vault token must be root-only"
          assert_file_contains ${vaultModule} 'chmod 0600 "\$TOKEN_FILE"' "persisted Vault token must be root-only"
          assert_file_contains ${vaultModule} 'chmod 0600 "\$TMP_ENV"' "temporary Vault env file must be root-only"
          assert_file_contains ${vaultModule} 'chmod 0600 "\$ENV_FILE"' "persisted Vault env file must be root-only"
          assert_file_contains ${vaultModule} 'rm -f .*runtimeEnvironmentFile.*runtimeTokenFile' "vault auth cleanup must remove runtime credential files"
        '';
      }
      {
        name = "managed-secrets-loads-vault-runtime-environment";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${managedSecretsModule} 'managedSecretsVaultEnvironmentFiles' "managed-secrets must collect Vault env files"
          assert_file_contains ${managedSecretsModule} 'vaultCfg\.client\.runtimeEnvironmentFile' "managed-secrets must consume runtime Vault environment"
          assert_file_contains ${managedSecretsModule} 'EnvironmentFile = managedSecretsVaultEnvironmentFiles' "managed-secrets service must load Vault env files"
          assert_file_contains ${managedSecretsModule} 'UMask = "0077"' "managed-secrets service must keep a restrictive umask"
          assert_file_contains ${managedSecretsModule} 'vault-auth-setup.service' "managed-secrets must integrate with vault auth bootstrap"
        '';
      }
      {
        name = "local-users-supports-sops-backed-client-password-hash";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${localUsersModule} 'clientPassword = with types' "local user policy must expose client password source"
          assert_file_contains ${localUsersModule} 'client-user-password-hash' "client password SOPS secret name must be explicit"
          assert_file_contains ${localUsersModule} 'sops.secrets' "client password hash must be declared as a SOPS secret"
          assert_file_contains ${localUsersModule} 'clientPassword.sops.secretName' "client password hash must use the configured SOPS secret name"
          assert_file_contains ${localUsersModule} 'neededForUsers = true' "SOPS-backed login hashes must be available before user creation"
        '';
      }
      {
        name = "lx-annotate-vault-secret-generators-remain-hostname-scoped";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${repoRoot}/modules/nixos/services/lx-annotate-local/options.nix 'vaultPathTemplate = mkOption' "vault path template option must exist"
          assert_file_contains ${lxAnnotateConfig} 'replaceStrings' "lx-annotate Vault secret generators must transform the configured path template"
          assert_file_contains ${lxAnnotateConfig} '"{hostname}"' "lx-annotate Vault secret generators must keep the hostname placeholder contract"
          assert_file_contains ${lxAnnotateConfig} 'config.networking.hostName' "lx-annotate Vault secret generators must derive the node name from networking.hostName"
          assert_file_contains ${lxAnnotateConfig} 'cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate' "lx-annotate Vault secret generators must use the configured Vault path template"
          assert_file_contains ${lxAnnotateConfig} 'vaultKeyField' "vault key field option must exist"
          assert_file_contains ${lxAnnotateConfig} 'vaultUuidField' "vault uuid field option must exist"
          assert_file_contains ${lxAnnotateConfig} 'vaultMasterKeyField' "vault master key field option must exist"
          assert_file_contains ${lxAnnotateConfig} 'manageMasterKey' "application master key provisioning must remain configurable"
        '';
      }
      {
        name = "lx-annotate-runtime-propagates-encryption-env-and-mount-gating";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateEnvScripts} 'export LX_ANNOTATE_ENCRYPTED_DATA_DIR=' "lx-annotate scripts must export the encrypted data dir"
          assert_file_contains ${lxAnnotateEnvScripts} 'export LX_ANNOTATE_MASTER_KEY_FILE=' "lx-annotate scripts must export the application master key file when configured"
          assert_file_contains ${lxAnnotateScripts} 'verify_encrypted_storage' "lx-annotate rebuild guard must validate encrypted storage with the application master key"
          assert_file_contains ${lxAnnotateConfig} 'RequiresMountsFor = \[ envDataDir \]' "lx-annotate services must require the encrypted data mount"
          assert_file_contains ${lxAnnotateConfig} 'encryptionServiceUnits' "lx-annotate config must derive shared encryption service dependencies"
          assert_file_contains ${lxAnnotateConfig} '\+\+ encryptionServiceUnits' "lx-annotate app units must append encryption service dependencies"
          assert_file_contains ${lxAnnotateConfig} 'cmp -s "\$SECRET_FILE" "\$TARGET_FILE"' "Vault master key refresh must refuse accidental app-key rotation"
        '';
      }
    ];
  };
}
