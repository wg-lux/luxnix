from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path("/home/admin/luxnix")
SCRIPTS_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "scripts.nix"
)


def _extract_function(function_name: str) -> str:
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    match = re.search(
        rf"{function_name}\(\) \{{\n(.*?)\n    \}}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, f"Could not locate {function_name} in scripts.nix"
    body = textwrap.dedent(match.group(1))
    body = re.sub(r"\$\{pkgs\.[^}]+\}/bin/([A-Za-z0-9_.+-]+)", r"\1", body)
    return f"{function_name}() {{\n{body}\n}}"


def _run_repair_gate(
    tmp_path: Path,
    *,
    use_encrypted_storage: str = "",
    master_key_file: str = "",
):
    helper_python = tmp_path / "python"
    helper_python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    helper_python.chmod(0o755)
    marker_file = tmp_path / "data_migration_repair_latest.log"
    calls_file = tmp_path / "calls.log"

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        use_wheel_runtime="true"
        repair_marker_file="{marker_file}"
        target_dir="{tmp_path / 'data'}"
        repoDir="{tmp_path / 'repo'}"

        write_repair_failure() {{
          printf 'failure:%s\\n' "$1" >> "{calls_file}"
        }}

        run_installed_django_command() {{
          printf 'django:%s\\n' "$*" >> "{calls_file}"
          printf 'repair-ok\\n'
        }}

        {_extract_function("repair_managed_runtime_payloads")}

        repair_managed_runtime_payloads "{helper_python}"
        """
    )

    env = os.environ.copy()
    if use_encrypted_storage:
        env["LX_ANNOTATE_USE_ENCRYPTED_STORAGE"] = use_encrypted_storage
    else:
        env.pop("LX_ANNOTATE_USE_ENCRYPTED_STORAGE", None)
    if master_key_file:
        env["LX_ANNOTATE_MASTER_KEY_FILE"] = master_key_file
    else:
        env.pop("LX_ANNOTATE_MASTER_KEY_FILE", None)
    env.pop("LX_ANNOTATE_MASTER_KEY", None)

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, marker_file, calls_file


def test_repair_managed_runtime_payloads_skips_when_encryption_is_not_configured(
    tmp_path: Path,
):
    result, marker_file, calls_file = _run_repair_gate(tmp_path)

    assert result.returncode == 0, result.stderr
    assert marker_file.read_text(encoding="utf-8").strip() == (
        "Skipping managed payload repair; encrypted storage is not configured for this runtime."
    )
    assert not calls_file.exists()


def test_repair_managed_runtime_payloads_runs_when_encryption_is_enabled(
    tmp_path: Path,
):
    result, marker_file, calls_file = _run_repair_gate(
        tmp_path,
        use_encrypted_storage="1",
    )

    assert result.returncode == 0, result.stderr
    assert "completed_at=" in marker_file.read_text(encoding="utf-8")
    assert "repair-ok" in marker_file.read_text(encoding="utf-8")
    assert calls_file.read_text(encoding="utf-8").splitlines() == [
        f"django:{tmp_path / 'python'} repair_managed_payloads",
    ]


def test_repair_managed_runtime_payloads_runs_when_master_key_is_configured(
    tmp_path: Path,
):
    result, marker_file, calls_file = _run_repair_gate(
        tmp_path,
        master_key_file="/run/secrets/lx-annotate-master-key",
    )

    assert result.returncode == 0, result.stderr
    assert "repair-ok" in marker_file.read_text(encoding="utf-8")
    assert calls_file.read_text(encoding="utf-8").splitlines() == [
        f"django:{tmp_path / 'python'} repair_managed_payloads",
    ]
