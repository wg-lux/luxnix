{
  pkgs,
  ntlib,
  repoRoot,
  ...
}:
let
  lxAnnotateModuleRoot = "${repoRoot}/modules/nixos/services/lx-annotate-local";
  lxAnnotateConfig = pkgs.writeText "lx-annotate-config-and-subservices.nix" (
    builtins.concatStringsSep "\n" (
      map builtins.readFile (
        [ "${lxAnnotateModuleRoot}/config.nix" ]
        ++ pkgs.lib.filesystem.listFilesRecursive "${lxAnnotateModuleRoot}/subservices"
      )
    )
  );
  lxAnnotateDiagnostics = "${repoRoot}/modules/nixos/services/lx-annotate-local/Diagnostics.md";
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
in
{
  suites."lx-annotate runtime reliability" = {
    pos = __curPos;
    tests = [
      {
        name = "lx-annotate-startup-chain-has-journal-namespace";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'lxAnnotateJournalNamespace = "lx-annotate"' "lx-annotate must register a dedicated journal namespace"
          assert_file_contains ${lxAnnotateConfig} 'LogNamespace = lxAnnotateJournalNamespace' "lx-annotate services must log to the dedicated namespace"
          assert_file_contains ${lxAnnotateDiagnostics} 'journalctl --namespace=lx-annotate -b' "diagnostics must document the startup-blocker journal query"
        '';
      }
      {
        name = "lx-annotate-required-base-data-fails-closed";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'exec .*lx-annotate-load-base-data' "base-data loading must propagate failure to systemd"
          if grep -q 'load-base-data failed; continuing' ${lxAnnotateConfig}; then
            fail "base-data failure must not permit workers or web to start"
          fi
        '';
      }
      {
        name = "lx-annotate-intake-has-level-triggered-retry";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'paths\.lx-annotate-filewatcher' "file intake must retain event-driven triggering"
          assert_file_contains ${lxAnnotateConfig} 'timers\.lx-annotate-filewatcher' "file intake must periodically retry pending files"
          assert_file_contains ${lxAnnotateConfig} 'OnUnitActiveSec = "5m"' "periodic intake reconciliation must have a bounded retry interval"
          assert_file_contains ${lxAnnotateConfig} 'Persistent = true' "missed intake retries must run after reboot"
        '';
      }
      {
        name = "lx-annotate-duplicate-cleanup-requires-real-mount";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'mountpoint -q "\$persisting_mount"' "active cleanup must verify a mounted persisting filesystem"
          assert_file_contains ${lxAnnotateConfig} 'findmnt -n -o TARGET --target "\$resolved_archive"' "active cleanup must resolve the archive mount target"
          assert_file_contains ${lxAnnotateConfig} 'archive is outside the persisting mount' "active cleanup must constrain archive ownership"
        '';
      }
      {
        name = "lx-annotate-wheel-runtime-has-one-installer";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateConfig} 'lx_annotate_wheel_ensure' "wheel runtime must own installation"
          assert_file_contains ${lxAnnotateScripts} 'lx-annotate-runtime-ensure' "service helpers must delegate installation"
          if grep -q 'wheel_installer_revision=' ${lxAnnotateScripts}; then
            fail "service helpers must not carry a second wheel installer"
          fi
        '';
      }
      {
        name = "lx-annotate-wheel-runtime-is-prepared-before-app-services";
        type = "script";
        script = ''
                    ${ntlib.helpers.path [ pkgs.gnugrep ]}
                    ${ntlib.helpers.scriptHelpers}
                    assert_file_contains ${lxAnnotateConfig} 'wheelRuntimePrepareServiceUnits = lib\.optionals useWheelRuntime' "wheel mode must declare one shared runtime preparation unit"
                    assert_file_contains ${lxAnnotateConfig} 'systemd\.services\.lx-annotate-wheel-runtime = mkIf useWheelRuntime' "wheel preparation must be a dedicated systemd oneshot"
                    assert_file_contains ${lxAnnotateConfig} 'ExecStart = ".*lx-annotate-runtime-ensure"' "the preparation unit must own wheel installation"
                    assert_file_contains ${lxAnnotateConfig} 'RemainAfterExit = false' "wheel preparation must not retain stale success across package upgrades"
                    assert_file_contains ${lxAnnotateConfig} 'export LX_ANNOTATE_WHEEL_INSTALL_ALLOWED=false' "application entrypoints must validate the prepared runtime without installing packages"
                    assert_file_contains ${lxAnnotateConfig} 'appServiceBaseRequires = \[' "application services must have a fail-closed dependency list"
                    assert_file_contains ${lxAnnotateConfig} '\+\+ wheelRuntimePrepareServiceUnits' "application services must wait for wheel preparation"
          #          assert_file_contains ${lxAnnotateDiagnostics} 'systemctl status lx-annotate-wheel-runtime\.service' "diagnostics must expose the wheel preparation unit"
        '';
      }
      {
        name = "lx-annotate-hls-backfill-reconciles-raw-and-processed-artifacts";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateScripts} 'run_hls_materialization both "\$@"' "default HLS reconciliation must delegate cross-artifact priority to the application"
          assert_file_contains ${lxAnnotateConfig} 'assertion = cfg\.hlsBackfill\.enable' "enabled LX-Annotate hosts must not opt out of prerequisite HLS replacement"
          assert_file_contains ${lxAnnotateConfig} 'assertion = cfg\.hlsBackfill\.extraArgs == \[ \]' "automatic production replacement must not be limited per machine"
          assert_file_contains ${lxAnnotateModuleRoot}/subservices/lx-annotate-hls-backfill.nix 'systemd\.timers\.lx-annotate-hls-backfill' "orphan reconciliation must recur without a reboot or user request"
          assert_file_contains ${lxAnnotateModuleRoot}/subservices/lx-annotate-hls-backfill.nix 'OnUnitInactiveSec = "1h"' "automatic HLS reconciliation must have a bounded recurrence interval"
          assert_file_contains ${lxAnnotateModuleRoot}/subservices/lx-annotate-hls-backfill.nix 'Persistent = true' "missed automatic HLS reconciliation must run after downtime"
          assert_file_contains ${lxAnnotateScripts} 'if \[ "\$explicit_artifact_kind" = "true" \]' "explicit raw-only or processed-only repair runs must remain supported"
          if grep -q 'artifact_kind_args=(--artifact-kind processed)' ${lxAnnotateScripts}; then
            fail "HLS reconciliation must not silently default to processed-only"
          fi
        '';
      }
      {
        name = "lx-annotate-nvenc-hls-has-an-isolated-worker-device";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateModuleRoot}/options/runtime.nix 'hlsEncodingProfile = mkOption' "HLS profile selection must be a typed runtime option"
          assert_file_contains ${lxAnnotateModuleRoot}/scripts/env.nix 'ENDOREG_HLS_ENCODING_PROFILE = cfg\.runtime\.hlsEncodingProfile' "the selected HLS profile must reach endoreg-db"
          assert_file_contains ${lxAnnotateConfig} 'cudaVisibleDevices = cfg\.runtime\.ffmpegWorker\.cudaVisibleDevices' "the FFmpeg worker must receive its isolated CUDA selector"
          assert_file_contains ${lxAnnotateConfig} 'hlsEncodingProfile != "clinical_h264_nvenc_cq_v1"' "NVENC selection must require an isolated worker GPU"
        '';
      }
      {
        name = "lx-annotate-monitoring-config-is-immutable-and-bounded";
        type = "script";
        script = ''
          ${ntlib.helpers.path [ pkgs.gnugrep ]}
          ${ntlib.helpers.scriptHelpers}
          assert_file_contains ${lxAnnotateModuleRoot}/options.nix 'options/monitoring\.nix' "the typed monitoring option module must be imported"
          assert_file_contains ${lxAnnotateConfig} 'lx-annotate-monitoring-config-v1\.json' "the monitoring inventory must be generated immutably"
          assert_file_contains ${lxAnnotateConfig} 'systemctl_path = "\$[{]pkgs\.systemd[}]/bin/systemctl"' "systemctl must be an absolute Nix store path"
          assert_file_contains ${lxAnnotateConfig} '< cfg\.runtime\.monitoring\.diskWarningFreePercent' "disk thresholds must be ordered"
          assert_file_contains ${lxAnnotateModuleRoot}/scripts/env.nix 'LX_ANNOTATE_MONITORING_CONFIG_FILE = monitoringConfigFile' "application services must receive the generated monitoring contract"
          assert_file_contains ${lxAnnotateConfig} 'LX_ANNOTATE_MONITORING_CONFIG_FILE.*cannot be overridden' "arbitrary monitoring config overrides must be rejected"
        '';
      }
    ];
  };
}
