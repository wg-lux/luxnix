{
  pkgs,
  ntlib,
  repoRoot,
  ...
}: let
  vaultModule = "${repoRoot}/modules/nixos/luxnix/vault/default.nix";
  managedSecretsModule = "${repoRoot}/modules/nixos/roles/managed-secrets/default.nix";
  lxAnnotateConfig = "${repoRoot}/modules/nixos/services/lx-annotate-local/config.nix";
in {
  suites."lx-annotate vault contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "vault-client-bootstrap-service-exists";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultModule} 'systemd\.services\.vault-auth-setup' "vault auth bootstrap service must exist"
          assert_file_contains ${vaultModule} 'runtimeEnvironmentFile' "vault runtime env file must be defined"
          assert_file_contains ${vaultModule} 'method = mkOption' "vault auth method option must exist"
          assert_file_contains ${vaultModule} 'tokenFile' "vault tokenFile auth must exist"
          assert_file_contains ${vaultModule} 'roleIdFile' "vault approle roleId must exist"
          assert_file_contains ${vaultModule} 'secretIdFile' "vault approle secretId must exist"
        '';
      }
      {
        name = "managed-secrets-handles-custom-secrets-atomically";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${managedSecretsModule} 'allManagedSecrets = .*activeBuiltinSecrets // activeCustomSecrets' "custom secrets must be included in generation set"
          assert_file_contains ${managedSecretsModule} 'refreshOnBoot = mkOption' "refreshOnBoot option must exist"
          assert_file_contains ${managedSecretsModule} 'mktemp "\$SECRET_DIR/\..*\.tmp\.' "secret refresh must use temp files"
          assert_file_contains ${managedSecretsModule} 'mv -f "\$TARGET_FILE" "\$SECRET_FILE"' "secret writes must be atomic"
          assert_file_contains ${managedSecretsModule} 'vault-auth-setup\.service' "managed-secrets must wait for vault auth bootstrap"
        '';
      }
      {
        name = "lx-annotate-vault-secrets-are-root-only-and-refreshed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
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
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'networking\.hostName to be set' "vault mode must require hostname"
          assert_file_contains ${lxAnnotateConfig} 'requires luxnix\.vault client configuration' "vault mode must require explicit vault client config"
          assert_file_contains ${lxAnnotateConfig} 'setupService' "lx-annotate must order after managed secrets setup"
          assert_file_contains ${lxAnnotateConfig} 'lx-annotate-master-key-check' "lx-annotate must validate the application master key before boot"
          assert_file_contains ${lxAnnotateConfig} 'masterKeyCheckUnits' "lx-annotate boot must require the master key guard"
        '';
      }
    ];
  };
}
