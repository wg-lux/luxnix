from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_lx_annotate_nix_eval_contract import _gc_02_contract, _nix_eval_expr_json


REPO_ROOT = Path("/home/admin/luxnix")
FILE_MOVER_SOURCE = REPO_ROOT / "modules/nixos/services/file_mover/default.nix"
LX_ANNOTATE_SCRIPTS_SOURCE = (
    REPO_ROOT / "modules/nixos/services/lx-annotate-local/scripts.nix"
)


def _environment_map(environment: list[str]) -> dict[str, str]:
    return {
        key: value
        for key, value in (entry.split("=", 1) for entry in environment if "=" in entry)
    }


def _nix_script_body(source: str, marker: str) -> str:
    marker_start = source.index(marker)
    body_start = source.index("''\n", marker_start) + 3
    body_end = source.index("\n  '';", body_start)
    return source[body_start:body_end]


def _file_mover_host_matrix() -> dict[str, Any]:
    return _nix_eval_expr_json(
        """
        let
          flake = builtins.getFlake "git+file:///home/admin/luxnix";
          lib = flake.inputs.nixpkgs.lib;
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
                  lxCfg.runtime.commands.transcodeVideo or null;
                inherit hasWatcherService hasWatcherPath;
                fileWatcherServiceConfig =
                  if hasWatcherService then
                    cfg.systemd.services."lx-annotate-filewatcher".serviceConfig
                  else
                    {};
                fileWatcherPathConfig =
                  if hasWatcherPath then
                    cfg.systemd.paths."lx-annotate-filewatcher".pathConfig
                  else
                    {};
                resolvedIntakeDirs = {
                  video = resolveRuntimeDataPath lxCfg.runtime.intakeDirs.video;
                  report = resolveRuntimeDataPath lxCfg.runtime.intakeDirs.report;
                  preanonymized =
                    resolveRuntimeDataPath lxCfg.runtime.intakeDirs.preanonymized;
                  sap = resolveRuntimeDataPath lxCfg.runtime.intakeDirs.sap;
                  moverStaging =
                    resolveRuntimeDataPath lxCfg.runtime.intakeDirs.moverStaging;
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
    assert watcher_env["WATCHER_VIDEO_DIR"] == resolved["video"]
    assert watcher_env["WATCHER_REPORT_DIR"] == resolved["report"]
    assert watcher_env["WATCHER_PREANONYMIZED_DIR"] == resolved["preanonymized"]
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
        assert transcode_command is not None, host_name
        assert "transcode_video" in transcode_command, host_name

        watcher_config = contract["fileWatcherServiceConfig"]
        watcher_path = contract["fileWatcherPathConfig"]
        watcher_env = _environment_map(watcher_config["Environment"])

        assert watcher_path["PathChanged"] == [
            resolved["video"],
            resolved["report"],
            resolved["preanonymized"],
        ], host_name
        assert resolved["moverStaging"] not in watcher_path["PathChanged"], host_name
        assert watcher_env["WATCHER_VIDEO_DIR"] == resolved["video"], host_name
        assert watcher_env["WATCHER_REPORT_DIR"] == resolved["report"], host_name
        assert (
            watcher_env["WATCHER_PREANONYMIZED_DIR"] == resolved["preanonymized"]
        ), host_name

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
            assert f'd "{path}" 0770 {user} {group} -' in tmpfiles, host_name


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
        source.index("        wait_for_input_ready() {") :
        source.index("        quarantine_unreadable_files() {")
    ]
    process_body = source[
        source.index("        process_input_dir() {") :
        source.index("        # Rsync with retry logic is not needed here")
    ]

    assert mover_config["CapabilityBoundingSet"] == ["CAP_CHOWN", "CAP_FOWNER"]
    assert mover_config["AmbientCapabilities"] == ["CAP_CHOWN", "CAP_FOWNER"]
    assert "normalize_source_permissions()" in source
    assert (
        wait_body.index('normalize_source_permissions "$source_dir"')
        < wait_body.index('source_has_files "$source_dir"')
    )
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
        assert f'd "{path}" 0770 {user} {group} -' in tmpfiles


def test_file_mover_stages_before_publishing_and_deletes_only_after_success() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    process_body = source[
        source.index("        process_input_dir() {") :
        source.index("        # Rsync with retry logic is not needed here")
    ]

    staging_index = process_body.index('staging_dir="${runtimeMoverStagingDir}/')
    rsync_index = process_body.index("/bin/rsync -av")
    publish_index = process_body.index("/bin/mv -f")
    publish_success_index = process_body.index('if [ "$publish_status" -eq 0 ]; then')
    source_delete_index = process_body.index('/bin/rm -f "\'\'${source_dir}/')

    assert staging_index < rsync_index < publish_index < publish_success_index
    assert publish_success_index < source_delete_index
    assert '"\'\'${source_dir}/" "\'\'${staging_dir}/"' in process_body
    assert '"\'\'${dest_dir}/\'\'${entry_name}"' in process_body


def test_file_mover_quarantines_unreadable_inputs_in_failed_input_dirs() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    failed_input_base = (
        'failedInputBaseDir = "${endoregPaths.storageBaseDir}/failed_input";'
    )
    quarantine_call = (
        'quarantine_unreadable_files "$source_dir" "$quarantine_dir" "$label"'
    )

    assert failed_input_base in source
    assert "quarantine_unreadable_files()" in source
    assert 'quarantine_target="\'\'${quarantine_dir}/' in source
    assert '/bin/mv -f "$unreadable_file" "$quarantine_target"' in source
    assert quarantine_call in source


def test_file_mover_video_validation_reports_permission_and_ffprobe_failures() -> None:
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    validation_body = source[
        source.index("        validate_video_sources() {") :
        source.index("        export_lx_annotate_transcode_env() {")
    ]

    assert '[ ! -r "$video_file" ]' in validation_body
    assert "not readable by ${endoregServiceUserName}" in validation_body
    assert "ffprobe rejected it" in validation_body
    assert "ffprobe_error_summary" in validation_body
    assert "2>&1 >/dev/null" in validation_body
    assert ">/dev/null 2>&1" not in validation_body
    assert 'return "$validation_status"' in validation_body


def test_file_mover_transcodes_video_before_publish() -> None:
    contract = _gc_02_contract()
    source = FILE_MOVER_SOURCE.read_text(encoding="utf-8")
    process_body = source[
        source.index("        process_input_dir() {") :
        source.index("        # Rsync with retry logic is not needed here")
    ]
    transcode_body = source[
        source.index("        transcode_video_entry() {") :
        source.index("        wait_for_input_ready() {")
    ]

    assert "transcode_video" in contract["commands"]["transcodeVideo"]
    assert "--settings=lx_annotate.settings.settings_prod" in contract["commands"][
        "transcodeVideo"
    ]
    assert "export_lx_annotate_transcode_env()" in source
    assert "LX_ANNOTATE_WHEEL_VENV" in source
    assert "WATCHER_VIDEO_DIR" in source
    assert "FFMPEG_TRANSCODE_TIMEOUT_SECONDS" in source
    assert "--input-dir" in source
    assert "--filename" in source
    assert "--output-dir" in source
    assert '"$input_dir" "$entry_name" "$dest_dir"' in source
    assert "--overwrite --json" in source
    assert (
        process_body.index('is_video_filename "$entry_name"')
        < process_body.index('transcode_video_entry "$staged_entry"')
        < process_body.index('/bin/mv -f "$staged_entry"')
    )
    assert "failed to transcode staged Video entry" in process_body
    assert "Published transcoded Video entry" in transcode_body
    assert "-pix_fmt" not in transcode_body
    assert "-color_range" not in transcode_body


def test_wheel_and_repo_filewatchers_process_existing_once() -> None:
    source = LX_ANNOTATE_SCRIPTS_SOURCE.read_text(encoding="utf-8")
    repo_marker = (
        'runLocalFileWatcherScript = '
        'pkgs.writeShellScriptBin "${watcherScriptName}"'
    )
    wheel_marker = (
        'runLocalFileWatcherWheelScript = '
        'pkgs.writeShellScriptBin "${watcherScriptName}"'
    )
    repo_body = _nix_script_body(
        source,
        repo_marker,
    )
    wheel_body = _nix_script_body(
        source,
        wheel_marker,
    )

    assert 'export LX_ANNOTATE_FILEWATCHER_ARGS="--process-existing-once"' in repo_body
    assert 'export LX_ANNOTATE_FILEWATCHER_ARGS="--process-existing-once"' in wheel_body
    assert "start-watcher" in repo_body
    assert "run-filewatcher" in repo_body
    assert "wheelFileWatcherOnceCommand" in wheel_body


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
            LX_ANNOTATE_SCRIPTS_SOURCE.read_text(encoding="utf-8"),
        ]
    )

    for legacy_path in (
        "/var/lib/lx-annotate/data/videos",
        "/var/lib/lx-annotate/data/report",
    ):
        assert legacy_path not in evaluated_contract
        assert legacy_path not in module_sources
