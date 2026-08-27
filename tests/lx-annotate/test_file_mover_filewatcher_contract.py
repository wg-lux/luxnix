from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nix_eval_helpers import eval_json as _nix_eval_expr_json
from test_lx_annotate_nix_eval_contract import _gc_02_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
FILE_MOVER_SOURCE = REPO_ROOT / "modules/nixos/services/file_mover/default.nix"
LX_ANNOTATE_CONFIG_SOURCE = (
    REPO_ROOT / "modules/nixos/services/lx-annotate-local/config.nix"
)
LX_ANNOTATE_ENV_SOURCE = (
    REPO_ROOT / "modules/nixos/services/lx-annotate-local/scripts/env.nix"
)


def _environment_map(environment: list[str]) -> dict[str, str]:
    return {
        key: value
        for key, value in (entry.split("=", 1) for entry in environment if "=" in entry)
    }


def _tmpfiles_declares_dir(
    tmpfiles: list[str], path: str, mode: str, user: str, group: str
) -> bool:
    return any(
        rule in tmpfiles
        for rule in (
            f'd "{path}" {mode} {user} {group} -',
            f"d {path} {mode} {user} {group} - -",
        )
    )


def _file_mover_host_matrix() -> dict[str, Any]:
    return _nix_eval_expr_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          lib = flake.inputs.nixpkgs.lib;
          envList = env: lib.mapAttrsToList (name: value: "${name}=${toString value}") env;
          hostNames = builtins.attrNames flake.nixosConfigurations;
          fileMoverEnabledHosts = lib.filter
            (hostName:
              flake.nixosConfigurations.${hostName}.config.services.luxnix.fileMover.enable
                or false)
            hostNames;
          mkHostContract = hostName:
            let
              cfg = flake.nixosConfigurations.${hostName}.config;
              lxCfg = cfg.services.luxnix.lxAnnotateLocal;
              runtimeDataDir = lxCfg.runtime.encryptedDataDir;
              resolveRuntimeDataPath = path:
                let
                  pathString = toString path;
                in
                if lib.hasPrefix "/" pathString then
                  pathString
                else if pathString == "data" then
                  runtimeDataDir
                else if lib.hasPrefix "data/" pathString then
                  "${runtimeDataDir}/${lib.removePrefix "data/" pathString}"
                else
                  "${runtimeDataDir}/${pathString}";
              hasWatcherService =
                builtins.hasAttr "lx-annotate-filewatcher" cfg.systemd.services;
              hasWatcherPath =
                builtins.hasAttr "lx-annotate-filewatcher" cfg.systemd.paths;
              hasWatcherTimer =
                builtins.hasAttr "lx-annotate-filewatcher" cfg.systemd.timers;
            in {
              name = hostName;
              value = {
                sourcePaths = {
                  video = cfg.roles.endoreg-client.paths.videoInputDir;
                  report = cfg.roles.endoreg-client.paths.pdfInputDir;
                };
                fileMoverServiceConfig =
                  cfg.systemd.services.move-my-files.serviceConfig;
                fileMoverPathConfig =
                  cfg.systemd.paths.move-my-files.pathConfig;
                transcodeVideoCommand =
                  cfg.services.luxnix.fileMover.videoTranscodeFallback.command;
                transcodeEnvironmentScript =
                  cfg.services.luxnix.fileMover.videoTranscodeFallback.environmentScript;
                inherit hasWatcherService hasWatcherPath hasWatcherTimer;
                fileWatcherAfter =
                  if hasWatcherService then
                    cfg.systemd.services."lx-annotate-filewatcher".after
                  else
                    [];
                fileWatcherRequires =
                  if hasWatcherService then
                    cfg.systemd.services."lx-annotate-filewatcher".requires
                  else
                    [];
                fileWatcherServiceConfig =
                  if hasWatcherService then
                    cfg.systemd.services."lx-annotate-filewatcher".serviceConfig
                    // {
                      Environment = envList cfg.systemd.services."lx-annotate-filewatcher".environment;
                    }
                  else
                    {};
                fileWatcherPathConfig =
                  if hasWatcherPath then
                    cfg.systemd.paths."lx-annotate-filewatcher".pathConfig
                  else
                    {};
                fileWatcherTimerConfig =
                  if hasWatcherTimer then
                    cfg.systemd.timers."lx-annotate-filewatcher".timerConfig
                  else
                    {};
                resolvedIntakeDirs = {
                  video = "${resolveRuntimeDataPath lxCfg.runtime.intakeDirs.importRoot}/video_import";
                  report = "${resolveRuntimeDataPath lxCfg.runtime.intakeDirs.importRoot}/report_import";
                  preanonymized = "${resolveRuntimeDataPath lxCfg.runtime.intakeDirs.importRoot}/preanonymized_import";
                  sap = "${resolveRuntimeDataPath lxCfg.runtime.intakeDirs.importRoot}/sap_import";
                  moverStaging = "${resolveRuntimeDataPath lxCfg.runtime.intakeDirs.importRoot}/.move-my-files-staging";
                };
                tmpfiles = cfg.systemd.tmpfiles.rules;
              };
            };
        in
          builtins.listToAttrs (map mkHostContract fileMoverEnabledHosts)
        """
    )


def test_file_mover_is_enabled_for_gc02_endoreg_client() -> None:
    file_mover = _gc_02_contract()["fileMover"]

    assert file_mover["enable"] is True
    assert file_mover["serviceConfig"]["Type"] == "oneshot"
    assert file_mover["path"]["wantedBy"] == ["multi-user.target"]
    assert file_mover["path"]["pathConfig"]["Unit"] == "move-my-files.service"


def test_file_mover_publishes_into_filewatcher_intake_contract() -> None:
    contract = _gc_02_contract()
    file_mover = contract["fileMover"]
    resolved = file_mover["resolvedIntakeDirs"]
    watcher_path = contract["fileWatcherPath"]["pathConfig"]
    watcher_env = _environment_map(contract["fileWatcherServiceConfig"]["Environment"])

    assert watcher_path["PathChanged"] == [
        resolved["video"],
        resolved["report"],
        resolved["preanonymized"],
    ]
    assert watcher_env["DATA_DIR"] == "/var/lib/lx-annotate/data"
    assert not any(key.startswith("WATCHER_") for key in watcher_env)
    assert resolved["moverStaging"] not in watcher_path["PathChanged"]


def test_all_file_mover_hosts_publish_into_filewatcher_intake_contract() -> None:
    matrix = _file_mover_host_matrix()

    assert matrix, "expected at least one file-mover-enabled host"

    for host_name, contract in matrix.items():
        resolved = contract["resolvedIntakeDirs"]
        source_paths = contract["sourcePaths"]
        mover_config = contract["fileMoverServiceConfig"]
        mover_path = contract["fileMoverPathConfig"]
        transcode_command = contract["transcodeVideoCommand"]

        assert contract["hasWatcherService"], host_name
        assert contract["hasWatcherPath"], host_name
        assert contract["hasWatcherTimer"], host_name
        assert transcode_command is not None, host_name
        assert "transcode_video" in transcode_command, host_name
        assert "LD_LIBRARY_PATH=" in contract["transcodeEnvironmentScript"], host_name

        watcher_config = contract["fileWatcherServiceConfig"]
        watcher_path = contract["fileWatcherPathConfig"]
        watcher_timer = contract["fileWatcherTimerConfig"]
        watcher_env = _environment_map(watcher_config["Environment"])

        # file_watcher.FileWatcherService requires all three intake directories
        # at construction time. In deployment it is deliberately invoked as a
        # bounded drain, not as the module's resident Observer loop.
        assert watcher_config["Type"] == "oneshot", host_name
        assert watcher_config["Restart"] == "no", host_name
        assert watcher_config["ExecStart"].endswith("/bin/lx-annotate-watch --once"), (
            host_name
        )
        assert "lx-annotate-load-base-data.service" in contract["fileWatcherAfter"], (
            host_name
        )
        assert "lx-annotate-master-key-check.service" in contract["fileWatcherAfter"], (
            host_name
        )
        assert (
            "lx-annotate-load-base-data.service" in contract["fileWatcherRequires"]
        ), host_name
        assert (
            "lx-annotate-master-key-check.service" in contract["fileWatcherRequires"]
        ), host_name

        assert watcher_path["PathChanged"] == [
            resolved["video"],
            resolved["report"],
            resolved["preanonymized"],
        ], host_name
        assert resolved["moverStaging"] not in watcher_path["PathChanged"], host_name
        assert watcher_env["DATA_DIR"].endswith("/data"), host_name
        assert not any(key.startswith("WATCHER_") for key in watcher_env), host_name

        # PathChanged handles normal arrivals. The periodic timer retries files
        # which were incomplete, temporarily unprocessable, or already present
        # when the path unit was activated.
        assert watcher_timer["Unit"] == "lx-annotate-filewatcher.service", host_name
        assert watcher_timer["Persistent"] is True, host_name
        assert watcher_timer["OnBootSec"] == "2m", host_name
        assert watcher_timer["OnUnitActiveSec"] == "5m", host_name

        assert mover_config["User"] == watcher_config["User"], host_name
        assert mover_config["Group"] == watcher_config["Group"], host_name
        mover_triggers = mover_path["DirectoryNotEmpty"]
        assert mover_triggers == [
            source_paths["video"],
            source_paths["report"],
        ], host_name
        assert resolved["video"] not in mover_triggers, host_name
        assert resolved["report"] not in mover_triggers, host_name
        assert resolved["moverStaging"] not in mover_triggers, host_name

        user = mover_config["User"]
        group = mover_config["Group"]
        tmpfiles = contract["tmpfiles"]

        for path in (
            resolved["video"],
            resolved["report"],
            resolved["preanonymized"],
            resolved["sap"],
        ):
            assert _tmpfiles_declares_dir(tmpfiles, path, "0770", user, group), (
                host_name
            )


def test_file_mover_path_triggers_only_on_operator_source_dirs() -> None:
    file_mover = _gc_02_contract()["fileMover"]
    source_paths = file_mover["sourcePaths"]
    resolved = file_mover["resolvedIntakeDirs"]
    path_config = file_mover["path"]["pathConfig"]

    assert path_config["DirectoryNotEmpty"] == [
        source_paths["video"],
        source_paths["report"],
    ]
    assert path_config["MakeDirectory"] is True
    assert resolved["video"] not in path_config["DirectoryNotEmpty"]
    assert resolved["report"] not in path_config["DirectoryNotEmpty"]
    assert resolved["preanonymized"] not in path_config["DirectoryNotEmpty"]


def test_file_mover_and_filewatcher_use_same_service_identity() -> None:
    contract = _gc_02_contract()
    mover_config = contract["fileMover"]["serviceConfig"]
    watcher_config = contract["fileWatcherServiceConfig"]

    assert mover_config["User"] == watcher_config["User"]
    assert mover_config["Group"] == watcher_config["Group"]
    assert mover_config["PermissionsStartOnly"] is True


def test_file_mover_can_repair_late_arriving_source_permissions() -> None:
    contract = _gc_02_contract()
    mover_config = contract["fileMover"]["serviceConfig"]
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    wait_body = source[
        source.index("        wait_for_input_ready() {") : source.index(
            "        quarantine_unreadable_files() {"
        )
    ]
    process_body = source[
        source.index("        process_input_dir() {") : source.index(
            "        # Rsync with retry logic is not needed here"
        )
    ]

    assert mover_config["CapabilityBoundingSet"] == ["CAP_CHOWN", "CAP_FOWNER"]
    assert mover_config["AmbientCapabilities"] == ["CAP_CHOWN", "CAP_FOWNER"]
    assert "normalize_source_permissions()" in source
    assert wait_body.index(
        'normalize_source_permissions "$source_dir"'
    ) < wait_body.index('source_has_files "$source_dir"')
    assert 'normalize_source_permissions "$source_dir"' in process_body
    assert "still unreadable after permission normalization" in wait_body


def test_tmpfiles_create_file_mover_handoff_dirs_with_service_ownership() -> None:
    contract = _gc_02_contract()
    file_mover = contract["fileMover"]
    user = file_mover["serviceConfig"]["User"]
    group = file_mover["serviceConfig"]["Group"]
    source_paths = file_mover["sourcePaths"]
    resolved = file_mover["resolvedIntakeDirs"]
    tmpfiles = contract["tmpfiles"]

    assert f'd "{source_paths["video"]}" 0770 root {group} -' in tmpfiles
    assert f'd "{source_paths["report"]}" 0770 root {group} -' in tmpfiles

    for path in (
        resolved["importRoot"],
        resolved["video"],
        resolved["report"],
        resolved["preanonymized"],
        resolved["sap"],
    ):
        assert _tmpfiles_declares_dir(tmpfiles, path, "0770", user, group)


def test_gc10_file_mover_transcode_fallback_exports_runtime_library_path() -> None:
    env_script = _nix_eval_expr_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = flake.nixosConfigurations.gc-10.config;
        in
          cfg.services.luxnix.fileMover.videoTranscodeFallback.environmentScript
        """
    )

    assert "LD_LIBRARY_PATH=" in env_script
    assert "-gcc-" in env_script
    assert "-lib/lib" in env_script


def test_file_mover_stages_before_publishing_and_deletes_only_after_success() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    process_body = source[
        source.index("        process_input_dir() {") : source.index(
            "        # Rsync with retry logic is not needed here"
        )
    ]

    staging_index = process_body.index('staging_dir="${runtimeMoverStagingDir}/')
    rsync_index = process_body.index("/bin/rsync -av")
    publish_index = process_body.index("/bin/mv -f")
    publish_success_index = process_body.index('if [ "$publish_status" -eq 0 ]; then')
    source_delete_index = process_body.index("/bin/rm -f \"''${source_dir}/")

    assert staging_index < rsync_index < publish_index < publish_success_index
    assert publish_success_index < source_delete_index
    assert "\"''${source_dir}/\" \"''${staging_dir}/\"" in process_body
    assert "\"''${dest_dir}/''${entry_name}\"" in process_body


def test_file_mover_quarantines_unreadable_inputs_in_failed_input_dirs() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    quarantine_call = (
        'quarantine_unreadable_files "$source_dir" "$quarantine_dir" "$label"'
    )

    assert 'default = "${endoregPaths.storageBaseDir}/failed_input/video";' in source
    assert 'default = "${endoregPaths.storageBaseDir}/failed_input/pdf";' in source
    assert "quarantine_unreadable_files()" in source
    assert "quarantine_target=\"''${quarantine_dir}/" in source
    assert '/bin/mv -f "$unreadable_file" "$quarantine_target"' in source
    assert quarantine_call in source


def test_file_mover_quarantines_symlink_inputs_without_dereferencing() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    process_body = source[
        source.index("        process_input_dir() {") : source.index(
            "        # Rsync with retry logic is not needed here"
        )
    ]
    symlink_call = 'quarantine_symlink_entries "$source_dir" "$quarantine_dir" "$label"'
    unreadable_call = (
        'quarantine_unreadable_files "$source_dir" "$quarantine_dir" "$label"'
    )

    assert "quarantine_symlink_entries()" in source
    assert "-type l -exec ${pkgs.coreutils}/bin/chgrp -h" in source
    assert 'find "$source_dir" -mindepth 1 ! -type l ! -group' in source
    assert "Quarantining instead of dereferencing" in source
    assert '/bin/mv -f "$symlink_entry" "$quarantine_target"' in source
    assert process_body.index(symlink_call) < process_body.index(unreadable_call)


def test_file_mover_video_validation_reports_permission_and_ffprobe_failures() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    validation_body = source[
        source.index("        validate_video_sources() {") : source.index(
            "        export_video_transcode_fallback_env() {"
        )
    ]

    assert '[ ! -r "$video_file" ]' in validation_body
    assert "not readable by ${serviceUserName}" in validation_body
    assert "ffprobe rejected it" in validation_body
    assert "ffprobe_error_summary" in validation_body
    assert "2>&1 >/dev/null" in validation_body
    assert ">/dev/null 2>&1" not in validation_body
    assert 'return "$validation_status"' in validation_body


def test_file_mover_quarantines_stale_ffprobe_rejected_videos() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    validation_body = source[
        source.index("        validate_video_sources() {") : source.index(
            "        export_video_transcode_fallback_env() {"
        )
    ]
    wait_body = source[
        source.index("        wait_for_input_ready() {") : source.index(
            "        quarantine_unreadable_files() {"
        )
    ]
    process_body = source[
        source.index("        process_input_dir() {") : source.index(
            "        # Rsync with retry logic is not needed here"
        )
    ]

    assert "ffprobe_reject_grace_seconds=1800" in wait_body
    assert 'local quarantine_dir="$2"' in wait_body
    assert 'local label="$3"' in wait_body
    assert (
        'validate_video_sources "$source_dir" "$quarantine_dir" '
        '"$ffprobe_reject_grace_seconds"'
    ) in wait_body
    assert (
        'wait_for_input_ready "$source_dir" "$quarantine_dir" "$label"' in process_body
    )
    assert "file_age=$((now_epoch - file_ctime))" in validation_body
    assert (
        'if [ "$file_age" -ge "$ffprobe_reject_grace_seconds" ]; then'
        in validation_body
    )
    assert "quarantine_target=\"''${quarantine_dir}/" in validation_body
    assert '/bin/mv -f "$video_file" "$quarantine_target"' in validation_body
    assert "Failed to quarantine ffprobe-rejected video input" in validation_body
    assert validation_body.index(
        'if [ "$file_age" -ge "$ffprobe_reject_grace_seconds" ]; then'
    ) < validation_body.index(
        'echo "Waiting: video input is readable but ffprobe rejected it for'
    )


def test_file_mover_transcodes_video_before_publish() -> None:
    contract = _gc_02_contract()
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    process_body = source[
        source.index("        process_input_dir() {") : source.index(
            "        # Rsync with retry logic is not needed here"
        )
    ]
    transcode_body = source[
        source.index("        transcode_video_entry() {") : source.index(
            "        wait_for_input_ready() {"
        )
    ]

    assert "transcode_video" in contract["fileMover"]["transcodeVideoCommand"]
    assert "export_video_transcode_fallback_env()" in source
    assert "DATA_DIR" in contract["fileMover"]["transcodeEnvironmentScript"]
    assert "FFMPEG_TRANSCODE_TIMEOUT_SECONDS" in source
    assert "--input-dir" in contract["fileMover"]["transcodeVideoCommand"]
    assert "--filename" in contract["fileMover"]["transcodeVideoCommand"]
    assert "--output-dir" in contract["fileMover"]["transcodeVideoCommand"]
    assert '"$input_dir" "$entry_name" "$dest_dir"' in source
    assert "--overwrite --json" in contract["fileMover"]["transcodeVideoCommand"]
    assert (
        process_body.index('is_video_filename "$entry_name"')
        < process_body.index('transcode_video_entry "$staged_entry"')
        < process_body.index('/bin/mv -f "$staged_entry"')
    )
    assert "failed to transcode staged Video entry" in process_body
    assert "Published transcoded Video entry" in transcode_body
    assert ") < /dev/null; then" in transcode_body
    assert "-pix_fmt" not in transcode_body
    assert "-color_range" not in transcode_body


def test_file_mover_transcode_fallback_fails_closed_before_publish() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    transcode_body = source[
        source.index("        transcode_video_entry() {") : source.index(
            "        wait_for_input_ready() {"
        )
    ]

    assert "video transcode command failed" in transcode_body
    assert (
        "video transcode command did not create a non-empty output file"
        in transcode_body
    )
    assert '[ ! -s "$output_file" ]' in transcode_body
    assert 'chgrp ${serviceGroup} "$output_file" || true' not in transcode_body
    assert 'chmod 0660 "$output_file" || true' not in transcode_body
    assert (
        transcode_body.index("if ! (")
        < transcode_body.index('[ ! -s "$output_file" ]')
        < transcode_body.index("chgrp ${serviceGroup}")
        < transcode_body.index("chmod 0660")
        < transcode_body.index("Published transcoded Video entry")
    )


def test_filewatcher_deployment_uses_packaged_once_entrypoint() -> None:
    source = LX_ANNOTATE_CONFIG_SOURCE.read_text(encoding="utf-8")

    assert "make_entrypoint lx-annotate-watch lx-annotate-watch 0" in source
    assert (
        'ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-watch --once";'
        in source
    )
    assert 'Type = "oneshot";' in source


def test_no_legacy_hardcoded_watcher_destinations_bypass_intake_dirs() -> None:
    contract = _gc_02_contract()
    evaluated_contract = json.dumps(
        {
            "fileMover": contract["fileMover"],
            "fileWatcherPath": contract["fileWatcherPath"],
            "fileWatcherEnvironment": contract["fileWatcherServiceConfig"][
                "Environment"
            ],
        },
        sort_keys=True,
    )
    module_sources = "\n".join(
        [
            FILE_MOVER_SOURCE.read_text(encoding="utf-8"),
            LX_ANNOTATE_CONFIG_SOURCE.read_text(encoding="utf-8"),
            LX_ANNOTATE_ENV_SOURCE.read_text(encoding="utf-8"),
        ]
    )

    for legacy_path in (
        "/var/lib/lx-annotate/data/videos",
        "/var/lib/lx-annotate/data/report",
    ):
        assert legacy_path not in evaluated_contract
        assert legacy_path not in module_sources
