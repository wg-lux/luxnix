from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "scripts.nix"
)


def _extract_function(function_name: str) -> str:
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    match = re.search(
        rf"^(?P<indent>[ \t]*){function_name}\(\) \{{\n",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Could not locate {function_name} in scripts.nix"
    indent = match.group("indent")
    lines = source[match.end() :].splitlines()
    body_lines: list[str] = []
    for line in lines:
        if line.rstrip() == f"{indent}}}":
            break
        body_lines.append(line)
    else:
        raise AssertionError(f"Could not locate end of {function_name} in scripts.nix")

    body = textwrap.dedent("\n".join(body_lines))
    body = body.replace("''${", "${")
    body = re.sub(r"\$\{pkgs\.[^}]+\}/bin/([A-Za-z0-9_.+-]+)", r"\1", body)
    return f"{function_name}() {{\n{body}\n}}"


def _run_repair_gate(
    tmp_path: Path,
    *,
    master_key_file: str | None = None,
):
    helper_python = tmp_path / "python"
    helper_python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    helper_python.chmod(0o755)
    marker_file = tmp_path / "data_migration_repair_latest.log"
    completion_marker_file = tmp_path / "managed_payload_repair_v2"
    calls_file = tmp_path / "calls.log"

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        use_wheel_runtime="true"
        repair_marker_file="{marker_file}"
        repair_revision="v2"
        repair_completion_marker_file="{completion_marker_file}"
        target_dir="{tmp_path / 'data'}"
        repoDir="{tmp_path / 'repo'}"
        unset LX_ANNOTATE_MASTER_KEY
        unset LX_ANNOTATE_MASTER_KEY_FILE
        {"export LX_ANNOTATE_MASTER_KEY_FILE=\"" + master_key_file + "\"" if master_key_file else ""}

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
    env.pop("LX_ANNOTATE_MASTER_KEY_FILE", None)
    env.pop("LX_ANNOTATE_MASTER_KEY", None)

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, marker_file, completion_marker_file, calls_file


def test_repair_managed_runtime_payloads_skips_when_master_key_is_not_configured(
    tmp_path: Path,
):
    result, marker_file, completion_marker_file, calls_file = _run_repair_gate(tmp_path)

    assert result.returncode == 0, result.stderr
    assert marker_file.read_text(encoding="utf-8").strip() == (
        "Skipping managed payload repair; LX_ANNOTATE_MASTER_KEY or LX_ANNOTATE_MASTER_KEY_FILE is not configured for this runtime."
    )
    assert not calls_file.exists()
    assert not completion_marker_file.exists()


def test_repair_managed_runtime_payloads_runs_when_master_key_is_configured(
    tmp_path: Path,
):
    result, marker_file, completion_marker_file, calls_file = _run_repair_gate(
        tmp_path,
        master_key_file="/run/secrets/lx-annotate-master-key",
    )

    assert result.returncode == 0, result.stderr
    assert "repair-ok" in marker_file.read_text(encoding="utf-8")
    assert completion_marker_file.read_text(encoding="utf-8").splitlines()[0] == (
        "repair_revision=v2"
    )
    assert calls_file.read_text(encoding="utf-8").splitlines() == [
        f"django:{tmp_path / 'python'} repair_managed_payloads",
    ]


def test_wheel_data_recovery_keeps_legacy_media_overlay_after_helper_success():
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    assert (
        'run_installed_django_command "${wheelVenvPythonPath}" migrate --noinput'
        in source
    )
    assert (
        'sync_source_dir "${cfg.dataRecovery.legacyDataDir}" "legacy data compatibility overlay"'
        in source
    )
    assert (
        'sync_source_dir "${cfg.dataRecovery.legacyMediaDir}" "legacy media compatibility overlay"'
        in source
    )
    assert 'migration_mark_eligible --apply' in source
    assert source.index('migration_mark_eligible --apply') < source.index(
        'updated_failed_upload_jobs='
    )
    assert source.index('updated_failed_upload_jobs=') < source.index(
        'reap_upload_job_sources'
    )


def test_data_recovery_versions_payload_repair_independently_of_legacy_recovery():
    source = SCRIPTS_NIX.read_text(encoding="utf-8")

    assert 'repair_revision="v2"' in source
    assert 'repair_completion_marker_file="$marker_dir/managed_payload_repair_$repair_revision"' in source
    assert "LX_ANNOTATE_FORCE_MANAGED_PAYLOAD_REPAIR" in source
    assert "skipping heavy legacy recovery" in source
    assert source.index('if [ "$run_heavy_recovery" = "true" ]; then') < source.index(
        'if [ "$run_managed_payload_repair" = "true" ]; then'
    )
