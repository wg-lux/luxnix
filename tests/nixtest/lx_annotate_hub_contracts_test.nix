{
  pkgs,
  ntlib,
  repoRoot,
  ...
}: let
  lxAnnotateOptions = "${repoRoot}/modules/nixos/services/lx-annotate-local/options.nix";
  lxAnnotateConfig = "${repoRoot}/modules/nixos/services/lx-annotate-local/config.nix";
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
in {
  suites."lx-annotate hub contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "lx-annotate-hub-default-is-gs-02-only";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateOptions} 'default = config\.networking\.hostName == "gs-02";' "lx-annotate hub mode must default only on gs-02"
          assert_file_contains ${lxAnnotateConfig} 'hub\.enable =\s*mkDefault \(config\.networking\.hostName == "gs-02"\);' "lx-annotate config must preserve gs-02 as the only default hub host"
        '';
      }
      {
        name = "lx-annotate-exports-endoreg-hub-env";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.gnugrep]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateScripts} 'export ENDOREG_HUB_MODE="\$\{' "lx-annotate shell runtime env must export ENDOREG_HUB_MODE"
          assert_file_contains ${lxAnnotateScripts} 'export ENDOREG_ENABLE_HUB_TRANSFERS="\$\{' "lx-annotate shell runtime env must export ENDOREG_ENABLE_HUB_TRANSFERS"
          assert_file_contains ${lxAnnotateScripts} 'export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT="\$\{' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT"
          assert_file_contains ${lxAnnotateScripts} 'export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS="\$\{' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_REQUIRE_MTLS"
          assert_file_contains ${lxAnnotateScripts} 'export ENDOREG_HUB_TRANSFER_MTLS_META_KEY=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_MTLS_META_KEY"
          assert_file_contains ${lxAnnotateScripts} 'export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE=' "lx-annotate shell runtime env must export ENDOREG_HUB_TRANSFER_MTLS_META_VALUE"
          assert_file_contains ${lxAnnotateScripts} 'ENDOREG_HUB_MODE=\$\{if cfg\.hub\.enable then "true" else "false"\}' "lx-annotate systemd env files must persist ENDOREG_HUB_MODE"
          assert_file_contains ${lxAnnotateScripts} 'ENDOREG_ENABLE_HUB_TRANSFERS=\$\{if cfg\.hub\.transferApi\.enable then "true" else "false"\}' "lx-annotate systemd env files must persist ENDOREG_ENABLE_HUB_TRANSFERS"
          assert_file_contains ${lxAnnotateScripts} 'ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT=\$\{if cfg\.hub\.transferApi\.requireSecureTransport then "true" else "false"\}' "lx-annotate systemd env files must persist ENDOREG_HUB_TRANSFER_REQUIRE_SECURE_TRANSPORT"
          assert_file_contains ${lxAnnotateScripts} 'ENDOREG_HUB_TRANSFER_REQUIRE_MTLS=\$\{if cfg\.hub\.transferApi\.requireMtls then "true" else "false"\}' "lx-annotate systemd env files must persist ENDOREG_HUB_TRANSFER_REQUIRE_MTLS"
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
          assert_file_contains ${lxAnnotateConfig} 'ssl_verify_client on;' "nginx must verify client certificates when transfer API is enabled"
        '';
      }
    ];
  };
}
