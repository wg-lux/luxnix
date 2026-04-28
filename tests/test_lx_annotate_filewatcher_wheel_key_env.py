from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path


SCRIPTS_NIX = Path(
    "/home/admin/dev/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix"
)


def _extract_wheel_filewatcher_script_body() -> str:
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    marker = 'runLocalFileWatcherWheelScript = pkgs.writeShellScriptBin "${watcherScriptName}"'
    start = source.find(marker)
    assert start != -1, "Could not locate wheel filewatcher script in scripts.nix"

    body_start = source.find("''\n", start)
    assert body_start != -1, "Could not locate start of wheel filewatcher script body"
    body_start += 3

    end = source.find("\n  '';", body_start)
    assert end != -1, (
        "Could not determine end of wheel filewatcher script in scripts.nix"
    )

    return source[body_start:end]


def test_wheel_filewatcher_exports_encryption_env_before_start():
    script_body = _extract_wheel_filewatcher_script_body()

    assert 'lx_annotate_export_wheel_service_env "${envDataDir}"' in script_body
    assert script_body.index(
        "lx_annotate_export_wheel_service_env"
    ) < script_body.index('exec "${pkgs.bash}/bin/bash" -lc')


def test_wheel_filewatcher_passes_master_key_file_to_child_process(tmp_path: Path):
    helper_script = tmp_path / "helpers.sh"
    helper_script.write_text(
        textwrap.dedent(
            """\
            lx_annotate_export_base_env() { :; }
            lx_annotate_export_storage_env() { :; }
            lx_annotate_export_encryption_env() {
              export LX_ANNOTATE_MASTER_KEY_FILE="${MASTER_KEY_FILE_PATH}"
            }
            lx_annotate_export_django_paths_env() { :; }
            lx_annotate_export_db_env() { :; }
            lx_annotate_export_secret_key_env() { :; }
            lx_annotate_export_oidc_env() { :; }
            lx_annotate_export_wheel_service_env() {
              local data_root="$1"
              lx_annotate_export_base_env
              lx_annotate_export_storage_env "$data_root"
              lx_annotate_export_encryption_env
              lx_annotate_export_django_paths_env
              lx_annotate_export_db_env
              export DJANGO_DJANGO_DB_PASSWORD="${DJANGO_DB_PASSWORD:-}"
              lx_annotate_export_secret_key_env
              lx_annotate_export_oidc_env
            }
            """
        ),
        encoding="utf-8",
    )

    runtime_venv = tmp_path / "wheel-venv"
    runtime_venv_bin = runtime_venv / "bin"
    runtime_venv_bin.mkdir(parents=True, exist_ok=True)
    (runtime_venv_bin / "python").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    (runtime_venv_bin / "python").chmod(0o755)

    child_output = tmp_path / "child-env.txt"
    django_static_root = tmp_path / "staticfiles"
    runtime_working_dir = tmp_path / "workdir"
    service_home = tmp_path / "home"
    runtime_root = tmp_path / "runtime-root"
    env_data_dir = tmp_path / "data"
    runtime_wheel_root = tmp_path / "wheel-app"
    master_key_file = tmp_path / "master.key"
    filewatcher_command = (
        f'env | grep "^LX_ANNOTATE_MASTER_KEY_FILE=" > "{child_output}"'
    )
    wheel_script = _extract_wheel_filewatcher_script_body()
    replacements = {
        "${lxAnnotateEnvHelpers}": str(helper_script),
        "${djangoStaticRootPath}": str(django_static_root),
        "${runtimeWorkingDir}": str(runtime_working_dir),
        "${endoreg-service-user-home}": str(service_home),
        "${runtimeRootPath}": str(runtime_root),
        "${envDataDir}": str(env_data_dir),
        "${cfg.runtime.tessdataPrefix}": "",
        "${cfg.runtime.pytorchAllocConf}": "",
        "${runtimeWheelVenvPath}": str(runtime_venv),
        "${runtimeWheelRootPath}": str(runtime_wheel_root),
        '${cfg.runtime.commands.fileWatcher or ""}': filewatcher_command,
        "${lib.escapeShellArg wheelFileWatcherCommand}": f'"{filewatcher_command}"',
    }
    for old, new in replacements.items():
        wheel_script = wheel_script.replace(old, new)
    wheel_script = wheel_script.replace(
        "${pkgs.bash}/bin/bash",
        "bash",
    )

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        MASTER_KEY_FILE_PATH="{master_key_file}"
        {wheel_script}
        """
    )

    env = os.environ.copy()
    env["MASTER_KEY_FILE_PATH"] = str(master_key_file)

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert child_output.read_text(encoding="utf-8").strip() == (
        f"LX_ANNOTATE_MASTER_KEY_FILE={master_key_file}"
    )
