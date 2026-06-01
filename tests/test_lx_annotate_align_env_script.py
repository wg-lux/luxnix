from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ASSETS_NIX = (
    REPO_ROOT
    / "modules"
    / "nixos"
    / "services"
    / "lx-annotate-local"
    / "scripts"
    / "frontend-assets.nix"
)


def _extract_align_env_script() -> str:
    source = FRONTEND_ASSETS_NIX.read_text(encoding="utf-8")
    match = re.search(
        r'alignEnvFileScript = pkgs\.writeText "lx-annotate-align-env\.py" \'\'\n(.*?)\n\s*\'\';',
        source,
        flags=re.DOTALL,
    )
    assert match is not None, "Could not locate alignEnvFileScript in frontend-assets.nix"
    return textwrap.dedent(match.group(1))


def _run_align_env_script(env_file: Path, *, desired_module: str, desired_env: str):
    env = os.environ.copy()
    env["LX_ANNOTATE_ENV_FILE"] = str(env_file)
    env["DESIRED_SETTINGS_MODULE"] = desired_module
    env["DESIRED_ENVIRONMENT"] = desired_env

    return subprocess.run(
        [sys.executable, "-c", _extract_align_env_script()],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_align_env_script_is_noop_when_env_file_is_missing(tmp_path: Path):
    missing_env = tmp_path / ".env"

    result = _run_align_env_script(
        missing_env,
        desired_module="lx_annotate.settings.settings_prod",
        desired_env="production",
    )

    assert result.returncode == 0
    assert not missing_env.exists()


def test_align_env_script_rewrites_existing_module_and_env(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DJANGO_SETTINGS_MODULE=lx_annotate.settings.settings_dev\n"
        "DJANGO_ENV=development\n"
        "KEEP_ME=1\n",
        encoding="utf-8",
    )

    result = _run_align_env_script(
        env_file,
        desired_module="lx_annotate.settings.settings_prod",
        desired_env="production",
    )

    assert result.returncode == 0
    assert env_file.read_text(encoding="utf-8") == (
        "DJANGO_SETTINGS_MODULE=lx_annotate.settings.settings_prod\n"
        "DJANGO_ENV=production\n"
        "KEEP_ME=1\n"
    )


def test_align_env_script_appends_missing_module_and_env(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("KEEP_ME=1\n", encoding="utf-8")

    result = _run_align_env_script(
        env_file,
        desired_module="lx_annotate.settings.settings_prod",
        desired_env="production",
    )

    assert result.returncode == 0
    assert env_file.read_text(encoding="utf-8") == (
        "KEEP_ME=1\n"
        "DJANGO_SETTINGS_MODULE=lx_annotate.settings.settings_prod\n"
        "DJANGO_ENV=production\n"
    )
