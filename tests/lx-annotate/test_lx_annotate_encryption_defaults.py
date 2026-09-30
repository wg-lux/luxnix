from __future__ import annotations

from pathlib import Path
import re
import os
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO_ROOT / "modules/nixos/services/lx-annotate-local"
SCRIPTS_NIX = SERVICE_DIR / "scripts.nix"
CONFIG_NIX = SERVICE_DIR / "config.nix"
OPTIONS_NIX = SERVICE_DIR / "options/runtime.nix"
SCRIPTS_ENV_NIX = SERVICE_DIR / "scripts/env.nix"


def _service_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((SERVICE_DIR / "subservices").rglob("*.nix"))
    )


def _has_assignment(source: str, name: str) -> bool:
    return re.search(rf"^\s*{re.escape(name)}\s*=", source, re.MULTILINE) is not None


RETIRED_MEDIA_PATH_VARIABLES = (
    "CONF_DIR",
    "CONF_TEMPLATE_DIR",
    "DATA_DIR",
    "STORAGE_DIR",
    "LX_ANNOTATE_DATA_DIR",
    "LX_ANNOTATE_ENCRYPTED_DATA_DIR",
    "PROTECTED_MEDIA_ROOT",
    "LX_ANNOTATE_STREAMABLE_VIDEO_ROOT",
    "LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT",
    "LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT",
)


@pytest.mark.parametrize("name", RETIRED_MEDIA_PATH_VARIABLES)
def test_service_does_not_reintroduce_retired_media_path_inputs(name: str) -> None:
    for path in SERVICE_DIR.rglob("*.nix"):
        source = path.read_text(encoding="utf-8")
        assert not _has_assignment(source, name), path
        assert re.search(rf"\bexport\s+{re.escape(name)}=", source) is None, path


@pytest.mark.parametrize(
    "root", ["/protected/runtime", "/protected/runtime with spaces"]
)
def test_storage_shell_helper_exports_only_canonical_root(root: str) -> None:
    source = SCRIPTS_ENV_NIX.read_text(encoding="utf-8")
    match = re.search(
        r"lx_annotate_export_storage_env\(\) \{(.*?)\n    \}", source, re.DOTALL
    )
    assert match is not None
    script = "lx_annotate_export_storage_env() {" + match.group(1) + "\n}\n"
    script += 'lx_annotate_export_storage_env "$1"\nenv -0'
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in RETIRED_MEDIA_PATH_VARIABLES
    }
    result = subprocess.run(
        ["bash", "-eu", "-c", script, "contract", root],
        env=environment,
        capture_output=True,
        check=True,
    )
    exports = dict(
        entry.split(b"=", 1) for entry in result.stdout.split(b"\0") if entry
    )
    assert exports[b"LX_RUNTIME_ROOT"] == root.encode()
    assert not set(name.encode() for name in RETIRED_MEDIA_PATH_VARIABLES).intersection(
        exports
    )


def test_repo_frame_export_uses_application_path_contract() -> None:
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    assert (
        'exec devenv shell -- lx-annotate-export-frames '
        '--output-dir "$exportFramesDir" --output-path "$exportFramesDir/frames.csv"'
        in source
    )


def test_lx_annotate_scripts_export_protected_storage_contract():
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    config_source = CONFIG_NIX.read_text(encoding="utf-8") + _service_source()
    options_source = OPTIONS_NIX.read_text(encoding="utf-8")
    helper_source = SCRIPTS_ENV_NIX.read_text(encoding="utf-8")

    assert "This is the lx-annotate environment contract." in helper_source
    assert "wheelRuntimePackage = pkgs.runCommand" in config_source
    assert "lx_annotate_wheel_ensure" in config_source
    assert "lx_annotate_wheel_sync_static" in config_source
    assert "lx_annotate_wheel_export_secret_env" in config_source
    assert (
        'DJANGO_SECRET_KEY="$(lx_annotate_wheel_read_required_secret' in config_source
    )
    assert 'DJANGO_DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD"' in config_source
    assert "PIP_CACHE_DIR" in config_source
    assert "pip-cache" in config_source
    assert "install --upgrade $pip_install_args" in config_source
    assert "wheelDependencyOverrides = mkOption" in options_source
    assert (
        "install --upgrade --no-deps $pip_install_args $wheel_dependency_overrides"
        in config_source
    )
    assert 'install --force-reinstall --no-deps "$staged_wheel_path"' in config_source
    assert "--no-cache-dir" not in config_source
    assert "package = effectiveRuntimePackage;" in config_source
    assert "make_entrypoint lx-annotate-web lx-annotate-web 1" in config_source
    assert (
        "find ${lib.escapeShellArg runtimeStaticRootPath} -type d -exec chmod 0750 {} +"
        in config_source
    )
    assert (
        "find ${lib.escapeShellArg runtimeStaticRootPath} -type f -exec chmod 0640 {} +"
        in config_source
    )
    assert (
        "chmod -R u+rwX,go-rwx ${lib.escapeShellArg runtimeStaticRootPath}"
        not in config_source
    )
    assert "make_entrypoint lx-annotate-migrate lx-annotate-migrate 0" in config_source
    assert "systemd = {" in config_source
    assert "services = {" in config_source
    assert "lx-annotate-migrate = mkLxAnnotateAppService" in config_source
    assert (
        "SupplementaryGroups = [ "
        "config.luxnix.generic-settings.sensitiveServiceGroupName ];" in config_source
    )
    assert (
        'pkgs.writeShellScript "lx-annotate-migrate-with-legacy-history-fallback"'
        in config_source
    )
    assert (
        "if ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput; then"
        in config_source
    )
    assert "lx-annotate-manage shell --command" in config_source
    assert (
        'call_command("repair_legacy_migration_history", apply=True)' in config_source
    )
    assert (
        "exec ${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput"
        in config_source
    )
    assert "ExecStartPre" not in config_source
    assert 'TimeoutStartSec = "2h";' in config_source
    assert (
        'ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-watch --once";'
        in config_source
    )
    assert (
        'ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-export-frames";'
        in config_source
    )
    assert "LX_RUNTIME_ROOT = envDataDir;" in helper_source
    assert "commonExtraEnv =" in config_source
    assert "// lib.optionalAttrs cfg.hub.transferApi.enable {" in config_source
    assert (
        "DJANGO_SECRET_KEY_FILE = toString cfg.django.djangoSecretKeyFile;"
        in helper_source
    )
    assert 'DJANGO_DB_PASSWORD_FILE = "${envConfDir}/db_pwd";' in helper_source

    assert not _has_assignment(config_source, "DATA_DIR")
    assert not _has_assignment(config_source, "LX_ANNOTATE_DATA_DIR")
    assert not _has_assignment(config_source, "PROTECTED_MEDIA_ROOT")
    assert not _has_assignment(config_source, "STORAGE_DIR")
    assert not _has_assignment(config_source, "LX_ANNOTATE_STREAMABLE_VIDEO_ROOT")
    assert not _has_assignment(config_source, "DJANGO_SETTINGS_MODULE")
    assert not _has_assignment(config_source, "DJANGO_ENV")
    assert not _has_assignment(config_source, "MEDIA_URL")

    assert 'export LX_RUNTIME_ROOT="$data_root"' in helper_source
    assert 'export LX_ANNOTATE_DATA_DIR="$data_root"' not in helper_source
    assert (
        'export PROTECTED_MEDIA_ROOT="${runtimeStorageRootPath}"' not in helper_source
    )
    assert 'export STORAGE_DIR="$data_root/storage"' not in helper_source
    assert (
        'export NGINX_PROTECTED_MEDIA_URL="${envNginxProtectedMediaUrl}"'
        not in helper_source
    )
    assert "PROTECTED_MEDIA_ROOT=${runtimeStorageRootPath}" not in source
    assert (
        "LX_ANNOTATE_STREAMABLE_VIDEO_ROOT=${runtimeStreamableVideoRootPath}"
        not in source
    )
