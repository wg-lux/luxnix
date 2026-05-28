{
  pkgs,
  ntlib,
  repoRoot,
  ...
}: let
  lxAnnotateOptions = "${repoRoot}/modules/nixos/services/lx-annotate-local/options.nix";
  lxAnnotateConfig = "${repoRoot}/modules/nixos/services/lx-annotate-local/config.nix";
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
  lxAnnotateEnvScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts/env.nix";
in {
  suites."lx-annotate hub contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "lx-annotate-hub-default-is-explicit-central-node";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateOptions} 'deploymentRole = mkOption' "lx-annotate must expose an explicit deployment role"
          assert_file_contains ${lxAnnotateOptions} 'LuxNix central server nodes map to central_hub' "deployment role docs must distinguish central servers from laptop center nodes"
          assert_file_contains ${lxAnnotateConfig} 'endoregCentralServer = lib\.attrByPath \[ "roles" "endoreg-db-central-01" "enable" \] false config;' "lx-annotate must derive central server classification from the central role"
          assert_file_contains ${lxAnnotateConfig} 'config\.networking\.hostName == "gs-02" \|\| endoregCentralServer' "lx-annotate hub mode must default for declared central nodes"
        '';
      }
      {
        name = "lx-annotate-exports-endoreg-hub-env";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_DEPLOYMENT_ROLE=.*envDeploymentRole' "lx-annotate shell runtime env must export ENDOREG_DEPLOYMENT_ROLE"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_MODE=' "lx-annotate shell runtime env must export ENDOREG_HUB_MODE"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_ENABLE_HUB_TRANSFERS=' "lx-annotate shell runtime env must export ENDOREG_ENABLE_HUB_TRANSFERS"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_MTLS_META_KEY=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_MTLS_META_KEY"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_DEPLOYMENT_ROLE=.*envDeploymentRole' "lx-annotate systemd env files must persist ENDOREG_DEPLOYMENT_ROLE"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_HUB_MODE=.*cfg\.hub\.enable' "lx-annotate systemd env files must persist ENDOREG_HUB_MODE"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_ENABLE_HUB_TRANSFERS=.*cfg\.hub\.transferApi\.enable' "lx-annotate systemd env files must persist ENDOREG_ENABLE_HUB_TRANSFERS"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=.*cfg\.hub\.transferApi\.requireSecureTransport' "lx-annotate systemd env files must persist ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=.*cfg\.hub\.transferApi\.requireMtls' "lx-annotate systemd env files must persist ENDOREG_HUB_TRANSFER_REQUIRE_MTLS"
        '';
      }
      {
        name = "lx-annotate-transfer-api-requires-hub";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateOptions} 'description = "Enable the authenticated node-to-node hub transfer API\. Disabled by default even on hub nodes\."' "transfer API option must stay explicit and default-off"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.enable' "transfer API must not be enabled outside hub mode"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.transferApi\.requireSecureTransport = true' "transfer API must require secure transport"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.transferApi\.requireMtls = true' "transfer API must require mTLS"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.transferApi\.clientCaFile to be set' "transfer API must require a client CA file"
          assert_file_contains ${lxAnnotateConfig} 'proxy_set_header X-Client-Cert-Verified \$ssl_client_verify;' "nginx must forward client certificate verification to Django"
          assert_file_contains ${lxAnnotateConfig} 'ssl_client_certificate \$[{]toString cfg\.hub\.transferApi\.clientCaFile};' "nginx must use the configured transfer client CA bundle"
          assert_file_contains ${lxAnnotateConfig} 'ssl_verify_client optional;' "nginx must request and verify supplied client certificates when transfer API is enabled"
        '';
      }
    ];
  };
}
