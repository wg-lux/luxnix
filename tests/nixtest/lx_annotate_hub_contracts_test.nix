{
  pkgs,
  ntlib,
  repoRoot,
  ...
}:
let
  lxAnnotateOptions = "${repoRoot}/modules/nixos/services/lx-annotate-local/options.nix";
  lxAnnotateConfig = "${repoRoot}/modules/nixos/services/lx-annotate-local/config.nix";
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
  lxAnnotateEnvScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts/env.nix";
  vaultConfig = "${repoRoot}/modules/nixos/luxnix/vault/default.nix";
in
{
  suites."lx-annotate hub contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "lx-annotate-hub-default-is-explicit-central-node";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateOptions} 'deploymentRole = mkOption' "lx-annotate must expose an explicit deployment role"
          assert_file_contains ${lxAnnotateOptions} 'LuxNix central server nodes map to central_hub' "deployment role docs must distinguish central servers from laptop center nodes"
          assert_file_contains ${lxAnnotateConfig} 'config\.networking\.hostName == "gs-02"' "lx-annotate hub mode must retain the declared gs-02 default"
          assert_file_contains ${lxAnnotateConfig} 'if cfg\.hub\.enable then "central_hub" else "site_node"' "lx-annotate deployment role must derive from its own hub contract"
          assert_file_contains ${lxAnnotateConfig} 'extraSettings\.IS_CENTRAL_NODE = mkIf cfg\.hub\.enable' "hub mode must set the Django central-node contract"
          assert_file_contains ${lxAnnotateConfig} 'mkForce true' "the central-node contract must override the site-role default"
        '';
      }
      {
        name = "lx-annotate-exports-endoreg-hub-env";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_DEPLOYMENT_ROLE=.*envDeploymentRole' "lx-annotate shell runtime env must export ENDOREG_DEPLOYMENT_ROLE"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_MODE=' "lx-annotate shell runtime env must export ENDOREG_HUB_MODE"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_ENABLE_INCOMING_HUB_TRANSFERS=' "lx-annotate shell runtime env must export ENDOREG_ENABLE_INCOMING_HUB_TRANSFERS"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_MTLS_META_KEY=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_MTLS_META_KEY"
          assert_file_contains ${lxAnnotateEnvScripts} 'export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_DEPLOYMENT_ROLE=.*envDeploymentRole' "lx-annotate systemd env files must persist ENDOREG_DEPLOYMENT_ROLE"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_HUB_MODE=.*cfg\.hub\.enable' "lx-annotate systemd env files must persist ENDOREG_HUB_MODE"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_ENABLE_INCOMING_HUB_TRANSFERS=.*cfg\.hub\.transferApi\.enable' "lx-annotate systemd env files must persist ENDOREG_ENABLE_INCOMING_HUB_TRANSFERS"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=.*cfg\.hub\.transferApi\.requireSecureTransport' "lx-annotate systemd env files must persist ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT"
          assert_file_contains ${lxAnnotateScripts} '^[[:space:]]*ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=.*cfg\.hub\.transferApi\.requireMtls' "lx-annotate systemd env files must persist ENDOREG_HUB_TRANSFER_REQUIRE_MTLS"
        '';
      }
      {
        name = "lx-annotate-transfer-api-requires-hub";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateOptions} 'description = "Enable the authenticated node-to-node hub transfer API\. Disabled by default even on hub nodes\."' "transfer API option must stay explicit and default-off"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.enable' "transfer API must not be enabled outside hub mode"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.transferApi\.requireSecureTransport = true' "transfer API must require secure transport"
          assert_file_contains ${lxAnnotateConfig} '^[[:space:]]*assertion = !cfg\.hub\.transferApi\.enable \|\| cfg\.hub\.transferApi\.requireMtls;' "transfer API must require mTLS"
          assert_file_contains ${lxAnnotateConfig} 'hub\.transferApi\.enable requires services\.luxnix\.lxAnnotateLocal\.hub\.transferApi\.clientCaFile to be set' "transfer API must require a client CA file"
          assert_file_contains ${lxAnnotateConfig} 'proxy_set_header X-Client-Cert-Verified \$ssl_client_verify;' "nginx must forward client certificate verification to Django"
          assert_file_contains ${lxAnnotateConfig} 'if [(]\$ssl_client_verify != SUCCESS[)]' "nginx must enforce verified client certificates on transfer locations"
          assert_file_contains ${lxAnnotateConfig} 'return 403;' "nginx must reject unverified transfer clients before proxying"
          assert_file_contains ${lxAnnotateConfig} 'recommendedProxySettings = true;' "nginx must provide the standard reverse-proxy headers"
          if grep -Eq 'proxy_set_header (Host|X-Forwarded-|X-Real-IP)' ${lxAnnotateConfig}; then
            fail "transfer-specific nginx config must not duplicate standard reverse-proxy headers"
          fi
          assert_file_contains ${lxAnnotateConfig} 'ssl_client_certificate \$[{]toString cfg\.hub\.transferApi\.clientCaFile};' "nginx must use the configured transfer client CA bundle"
          assert_file_contains ${lxAnnotateConfig} 'ssl_verify_client optional;' "nginx must request and verify supplied client certificates when transfer API is enabled"
        '';
      }
      {
        name = "lx-annotate-outbound-transfer-requires-mtls-identity";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateOptions} 'outboundTransfer = mkOption' "site nodes must expose explicit outbound transfer configuration"
          assert_file_contains ${lxAnnotateConfig} 'outboundTransfer\.enable requires runtime\.deploymentRole = \\"site_node\\"' "outbound transfer must be site-node-only"
          assert_file_contains ${lxAnnotateConfig} '^[[:space:]]*assertion = !cfg\.hub\.outboundTransfer\.enable \|\| cfg\.hub\.outboundTransfer\.requireMtls;' "outbound transfer must require mTLS"
          assert_file_contains ${lxAnnotateConfig} 'outboundTransfer\.enable requires an outbound client certificate file' "outbound transfer must require a client certificate"
          assert_file_contains ${lxAnnotateConfig} 'outboundTransfer\.enable requires an outbound client key file' "outbound transfer must require a client key"
          assert_file_contains ${lxAnnotateConfig} 'outboundTransfer\.enable requires a source-node secret file' "outbound transfer must require request authentication"
          assert_file_contains ${lxAnnotateEnvScripts} 'LX_ANNOTATE_HUB_EXPORT_CLIENT_CERT_FILE' "client certificate path must reach the worker environment"
          assert_file_contains ${lxAnnotateEnvScripts} 'LX_ANNOTATE_HUB_SOURCE_NODE_SECRET_FILE' "node secret file path must reach the worker environment"
          assert_file_contains ${lxAnnotateEnvScripts} 'CELERY_HUB_TRANSFER_QUEUE = celeryHubTransferQueueName' "hub transfer tasks must have a dedicated queue"
          assert_file_contains ${lxAnnotateEnvScripts} 'LX_ANNOTATE_HUB_EXPORT_STALE_AFTER_SECONDS' "stale recovery bounds must reach the worker environment"
          assert_file_contains ${lxAnnotateEnvScripts} 'LX_ANNOTATE_HUB_EXPORT_REQUEST_TIMEOUT_SECONDS' "long-running HTTP timeout must reach the worker environment"
          assert_file_contains ${lxAnnotateConfig} 'staleAfterSeconds > cfg\.hub\.outboundTransfer\.requestTimeoutSeconds' "stale recovery must not race an active transfer request"
          assert_file_contains ${lxAnnotateConfig} 'unitName = "lx-annotate-celery-hub-transfer-worker"' "outbound transfer must use a dedicated worker"
          assert_file_contains ${lxAnnotateConfig} 'dispatch_hub_export_recovery' "site nodes must periodically dispatch stale transfer recovery"
          assert_file_contains ${lxAnnotateConfig} 'systemd\.timers\.lx-annotate-hub-export-recovery' "outbound recovery must be level-triggered by a persistent timer"
          assert_file_contains ${lxAnnotateConfig} 'check_hub_export_health' "site nodes must classify transfer failures without exposing request payloads"
          assert_file_contains ${lxAnnotateConfig} 'systemd\.timers\.lx-annotate-hub-export-health' "site nodes must periodically surface classified transfer health"
        '';
      }
      {
        name = "vault-managed-server-tls-reloads-consumers";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${vaultConfig} 'before = \[ "vault\.service" \] \+\+ lib\.optional config\.services\.nginx\.enable "nginx\.service";' "managed TLS identity must exist before Vault and nginx start"
          assert_file_contains ${vaultConfig} 'requiredBy = \[ "vault\.service" \] \+\+ lib\.optional config\.services\.nginx\.enable "nginx\.service";' "Vault and nginx must require their managed TLS identity"
          assert_file_contains ${vaultConfig} 'systemctl kill --kill-whom=main --signal=HUP vault\.service' "Vault must reload a rotated server identity"
          assert_file_contains ${vaultConfig} 'systemctl reload nginx\.service' "nginx must reload a rotated server identity"
        '';
      }
    ];
  };
}
