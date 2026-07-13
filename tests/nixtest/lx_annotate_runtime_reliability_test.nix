{
  pkgs,
  ntlib,
  repoRoot,
  ...
}:
let
  lxAnnotateConfig = "${repoRoot}/modules/nixos/services/lx-annotate-local/config.nix";
  lxAnnotateScripts = "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts.nix";
in
{
  suites."lx-annotate runtime reliability" = {
    pos = __curPos;
    tests = [
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
          assert_file_contains ${lxAnnotateConfig} 'systemd\.paths\.lx-annotate-filewatcher' "file intake must retain event-driven triggering"
          assert_file_contains ${lxAnnotateConfig} 'systemd\.timers\.lx-annotate-filewatcher' "file intake must periodically retry pending files"
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
          assert_file_contains ${lxAnnotateScripts} 'mountpoint -q "\$persisting_mount"' "exported cleanup helper must fail closed on a plain directory"
          assert_file_contains ${lxAnnotateScripts} 'archive is outside the persisting mount' "exported cleanup helper must constrain archive ownership"
        '';
      }
    ];
  };
}
