{
  pkgs,
  ntlib,
  repoRoot,
  ...
}:
let
  vaultModule = "${repoRoot}/modules/nixos/luxnix/vault/default.nix";
  vaultAuthClassifier = "${repoRoot}/scripts/vault/classify-auth-error.sh";
  vaultServerTlsScript = "${repoRoot}/scripts/vault/maintain-server-tls.sh";
  managedSecretsModule = "${repoRoot}/modules/nixos/roles/managed-secrets/default.nix";
  localUsersModule = "${repoRoot}/modules/nixos/security/local-users/default.nix";
  lxAnnotateModuleRoot = "${repoRoot}/modules/nixos/services/lx-annotate-local";
  lxAnnotateConfig = pkgs.writeText "lx-annotate-config-and-subservices.nix" (
    builtins.concatStringsSep "\n" (
      map builtins.readFile (
        [ "${lxAnnotateModuleRoot}/config.nix" ]
        ++ pkgs.lib.filesystem.listFilesRecursive "${lxAnnotateModuleRoot}/subservices"
      )
    )
  );
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
  lxAnnotateEnvScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts/env.nix";
in
{
  suites."vault secret delivery contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "vault-runtime-files-are-root-only-and-ephemeral";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
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
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${managedSecretsModule} 'managedSecretsVaultEnvironmentFiles' "managed-secrets must collect Vault env files"
          assert_file_contains ${managedSecretsModule} 'vaultCfg\.client\.runtimeEnvironmentFile' "managed-secrets must consume runtime Vault environment"
          assert_file_contains ${vaultModule} 'runtimeStatusFile = mkOption' "Vault must expose its non-secret runtime status path"
          assert_file_contains ${managedSecretsModule} 'vaultCfg\.client\.runtimeStatusFile' "managed-secrets must consume the centralized Vault status path"
          assert_file_contains ${managedSecretsModule} 'EnvironmentFile = managedSecretsVaultEnvironmentFiles' "managed-secrets service must load Vault env files"
          assert_file_contains ${managedSecretsModule} 'UMask = "0077"' "managed-secrets service must keep a restrictive umask"
          assert_file_contains ${managedSecretsModule} 'vault-auth-setup.service' "managed-secrets must integrate with vault auth bootstrap"
        '';
      }
      {
        name = "vault-approle-credentials-never-enter-process-arguments";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'TMP_AUTH=.*mktemp.*\.vault-approle' "AppRole login must use a private temporary payload"
          assert_file_contains ${vaultModule} 'chmod 0600 "\$TMP_AUTH"' "AppRole payload must be root-only"
          assert_file_contains ${vaultModule} '^[[:space:]]*printf .*\$ROLE_ID.*\$SECRET_ID' "AppRole values must enter the encoder through Bash's in-process printf builtin"
          assert_file_contains ${vaultModule} 'jq -Rn' "AppRole JSON must be encoded from stdin"
          assert_file_contains ${vaultModule} 'auth/approle/login @"\$TMP_AUTH"' "Vault login must receive only the payload filename as an argument"
          if grep -Eq 'role_id="\$ROLE_ID"|secret_id="\$SECRET_ID"|--arg[^[:cntrl:]]*(ROLE_ID|SECRET_ID)|/bin/printf[^[:cntrl:]]*(ROLE_ID|SECRET_ID)' ${vaultModule}; then
            echo "AppRole credentials must never be interpolated into child-process arguments" >&2
            exit 1
          fi
        '';
      }
      {
        name = "vault-initial-enrollment-can-defer-while-lx-annotate-stays-fail-closed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'deferUntilProvisioned = mkOption' "Vault must expose an explicit temporary enrollment mode"
          assert_file_contains ${vaultModule} 'ExecCondition = lib\.optionals cfg\.client\.auth\.deferUntilProvisioned' "temporary enrollment must use a non-failing systemd condition"
          assert_file_contains ${vaultModule} 'if ! .*vaultAuthSetupScript.*; then' "temporary enrollment condition must test the real Vault login"
          assert_file_contains ${vaultModule} 'if cfg\.client\.auth\.deferUntilProvisioned then' "temporary mode must avoid performing AppRole login twice"
          assert_file_contains ${vaultModule} 'lx-annotate remains fail-closed until its Vault enrollment bundle is installed' "the skipped unit must explain the application safety state"
          assert_file_contains ${vaultModule} 'After installing the bundle, run: systemctl start vault-auth-setup\.service' "the skipped unit must provide its recovery command"
          assert_file_contains ${vaultModule} 'luxnix-vault-classify-auth-error' "deferred auth must use the tested non-secret state classifier"
          assert_file_contains ${vaultAuthClassifier} 'tls-trust-failed' "deferred auth must expose TLS trust failures explicitly"
          assert_file_contains ${vaultAuthClassifier} 'vault-sealed' "deferred auth must distinguish a sealed Vault"
          assert_file_contains ${vaultAuthClassifier} 'vault-unreachable' "deferred auth must distinguish network unavailability"
          assert_file_contains ${vaultAuthClassifier} 'auth-rejected' "deferred auth must distinguish rejected authentication"
          assert_file_contains ${vaultAuthClassifier} 'Vault is sealed' "sealed detection must use Vault's explicit response"
          assert_file_contains ${vaultModule} 'Run luxnix-vault-enrollment-status for safe recovery guidance' "the journal must direct operators to non-secret diagnostics"
          if grep -Eq 'cat "\$auth_error"' ${vaultModule}; then
            echo "Raw Vault authentication errors must not be replayed into the journal." >&2
            exit 1
          fi
          assert_file_contains ${vaultModule} 'luxnix-vault-enrollment-status' "operators must have a non-secret enrollment status command"
          assert_file_contains ${managedSecretsModule} 'Vault runtime credentials are unavailable.*managed secrets remain fail-closed' "managed-secrets must fail clearly when vault.env is absent"
          assert_file_contains ${managedSecretsModule} '"-\$[^" ]*runtimeEnvironmentFile' "the optional systemd env load must allow the explicit fail-closed check to run"
          gpu_client_vars=${repoRoot}/ansible/inventory/group_vars/gpu_client.yml
          assert_file_contains "$gpu_client_vars" 'networking\.hosts\."172\.16\.255\.22"' "GPU clients must resolve Vault through the declared VPN path"
          if grep -q 'vault\.client\.auth\.deferUntilProvisioned' "$gpu_client_vars"; then
            echo "The temporary Vault enrollment gate must be host-scoped, not fleet-wide." >&2
            exit 1
          fi
          for host in gc-02 gc-04 gc-05 gc-06 gc-07 gc-08 gc-09 gc-10; do
            assert_file_contains \
              "${repoRoot}/ansible/inventory/host_vars/$host.yml" \
              'vault\.client\.auth\.deferUntilProvisioned: "true"' \
              "$host must explicitly record its temporary enrollment state"
          done
        '';
      }
      {
        name = "vault-server-leaf-rotates-under-a-stable-ca";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'managedTls = mkOption' "Vault must expose the stable-CA server TLS lifecycle"
          assert_file_contains ${vaultModule} 'scripts/vault/maintain-server-tls\.sh' "the module must use the directly testable TLS lifecycle script"
          assert_file_contains ${vaultServerTlsScript} 'refusing automatic CA replacement' "automatic renewal must never replace an existing or invalid CA"
          assert_file_contains ${vaultServerTlsScript} 'openssl x509 -req' "server leaves must be CA-signed"
          assert_file_contains ${vaultServerTlsScript} 'openssl verify -CAfile "\$ca_cert" -purpose sslserver' "renewed leaves must verify under the stable CA"
          assert_file_contains ${vaultModule} 'cp .*serverCfg\.caCertFile.*"\$server_ca_tmp"' "enrollment must publish the CA, not the server leaf"
          assert_file_contains ${vaultModule} 'Vault CA fingerprint mismatch; refusing installation' "migration must pin the trusted gs-02 fingerprint"
          if grep -Eq 'cp .*serverCfg\.tlsCertFile.*server_ca_tmp' ${vaultModule}; then
            echo "The renewable Vault server leaf must never be enrolled as a client trust anchor." >&2
            exit 1
          fi
          assert_file_contains ${repoRoot}/ansible/inventory/host_vars/gs-02.yml 'vault\.server\.caCertFile:.*luxnix-vault-pki/ca\.crt' "gs-02 must use the persistent CA path"
          assert_file_contains ${repoRoot}/ansible/inventory/host_vars/gs-02.yml 'vault\.server\.tlsCertFile:.*luxnix-vault-pki/server\.crt' "gs-02 must keep the renewable leaf separate"
          assert_file_contains ${repoRoot}/ansible/inventory/host_vars/gs-02.yml 'vault\.server\.managedTls\.enable: "true"' "gs-02 must enable managed leaf renewal"
        '';
      }
      {
        name = "local-users-supports-sops-backed-client-password-hash";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
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
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${repoRoot}/modules/nixos/services/lx-annotate-local/options/runtime.nix 'vaultPathTemplate = mkOption' "vault path template option must exist"
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
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateEnvScripts} 'export LX_ANNOTATE_ENCRYPTED_DATA_DIR=' "lx-annotate scripts must export the encrypted data dir"
          assert_file_contains ${lxAnnotateEnvScripts} 'export LX_ANNOTATE_MASTER_KEY_FILE=' "lx-annotate scripts must export the application master key file when configured"
          assert_file_contains ${lxAnnotateScripts} 'require_file_backed_master_key' "lx-annotate scripts must enforce the file-backed master key contract"
          assert_file_contains ${lxAnnotateScripts} 'LX_ANNOTATE_MASTER_KEY must not be set in production' "lx-annotate scripts must reject an inline master key that would override the key file"
          assert_file_contains ${lxAnnotateScripts} 'key_stat\.st_uid != 0' "lx-annotate scripts must require a root-owned application master key file"
          assert_file_contains ${lxAnnotateScripts} 'key_mode & 0o007' "lx-annotate scripts must reject application master key access for unrelated users"
          assert_file_contains ${lxAnnotateScripts} 'decoded_key.*16, 24, 32' "lx-annotate scripts must validate the decoded AES key length"
          assert_file_contains ${lxAnnotateScripts} 'runLocalHlsMaterializationScript.*pkgs\.writeShellScriptBin' "lx-annotate must provide the guarded HLS materialization wrapper"
          assert_file_contains ${lxAnnotateScripts} 'verify_encrypted_storage' "lx-annotate rebuild guard must validate encrypted storage with the application master key"
          assert_file_contains ${lxAnnotateConfig} 'ExecStart =.*runLocalMasterKeyCheckScript' "the master key systemd gate must execute the guarded wrapper"
          assert_file_contains ${lxAnnotateConfig} 'unitConfig = encryptedDataMountUnitConfig' "lx-annotate services must apply the shared encrypted-data mount contract"
          assert_file_contains ${lxAnnotateConfig} 'encryptionServiceUnits' "lx-annotate config must derive shared encryption service dependencies"
          assert_file_contains ${lxAnnotateConfig} '\+\+ encryptionServiceUnits' "lx-annotate app units must append encryption service dependencies"
          assert_file_contains ${lxAnnotateConfig} 'cmp -s "\$SECRET_FILE" "\$TARGET_FILE"' "Vault master key refresh must refuse accidental app-key rotation"
        '';
      }
    ];
  };
}
