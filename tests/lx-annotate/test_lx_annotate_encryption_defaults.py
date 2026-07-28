from __future__ import annotations

from pathlib import Path
import re


SCRIPTS_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix"
)
CONFIG_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/config.nix"
)
OPTIONS_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/options.nix"
)
SCRIPTS_ENV_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/scripts/env.nix"
)


def _has_assignment(source: str, name: str) -> bool:
    return re.search(rf"^\s*{re.escape(name)}\s*=", source, re.MULTILINE) is not None


def test_lx_annotate_scripts_export_protected_storage_contract():
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    config_source = CONFIG_NIX.read_text(encoding="utf-8")
    options_source = OPTIONS_NIX.read_text(encoding="utf-8")
    helper_source = SCRIPTS_ENV_NIX.read_text(encoding="utf-8")

    assert "This is the lx-annotate environment contract." in helper_source
    assert "wheelRuntimePackage = pkgs.runCommand" in config_source
    assert "lx_annotate_wheel_ensure" in config_source
    assert "lx_annotate_wheel_sync_static" in config_source
    assert "lx_annotate_wheel_export_secret_env" in config_source
    assert "DJANGO_SECRET_KEY=\"$(lx_annotate_wheel_read_required_secret" in config_source
    assert "DJANGO_DJANGO_DB_PASSWORD=\"$DJANGO_DB_PASSWORD\"" in config_source
    assert "PIP_CACHE_DIR" in config_source
    assert "pip-cache" in config_source
    assert "install --upgrade $pip_install_args" in config_source
    assert "wheelDependencyOverrides = mkOption" in options_source
    assert "install --upgrade --no-deps $pip_install_args $wheel_dependency_overrides" in config_source
    assert "--force-reinstall" not in config_source
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
    assert "chmod -R u+rwX,go-rwx ${lib.escapeShellArg runtimeStaticRootPath}" not in config_source
    assert "make_entrypoint lx-annotate-migrate lx-annotate-migrate 0" in config_source
    assert "systemd.services.lx-annotate-migrate = mkLxAnnotateAppService" in config_source
    assert "SupplementaryGroups = [ config.luxnix.generic-settings.sensitiveServiceGroupName ];" in config_source
    assert 'ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage migrate --noinput";' in config_source
    assert 'TimeoutStartSec = "2h";' in config_source
    assert 'ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-watch --once";' in config_source
    assert 'ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-export-frames";' in config_source
    assert "LX_ANNOTATE_ENCRYPTED_DATA_DIR = envDataDir;" in helper_source
    assert "commonExtraEnv = commonEnv;" in config_source
    assert "DJANGO_SECRET_KEY_FILE = toString cfg.django.djangoSecretKeyFile;" in helper_source
    assert 'DJANGO_DB_PASSWORD_FILE = "${envConfDir}/db_pwd";' in helper_source

    assert not _has_assignment(config_source, "DATA_DIR")
    assert not _has_assignment(config_source, "LX_ANNOTATE_DATA_DIR")
    assert not _has_assignment(config_source, "PROTECTED_MEDIA_ROOT")
    assert not _has_assignment(config_source, "STORAGE_DIR")
    assert not _has_assignment(config_source, "LX_ANNOTATE_STREAMABLE_VIDEO_ROOT")
    assert not _has_assignment(config_source, "DJANGO_SETTINGS_MODULE")
    assert not _has_assignment(config_source, "DJANGO_ENV")
    assert not _has_assignment(config_source, "MEDIA_URL")

    assert 'export DATA_DIR="$data_root"' not in helper_source
    assert 'export LX_ANNOTATE_DATA_DIR="$data_root"' not in helper_source
    assert 'export PROTECTED_MEDIA_ROOT="${runtimeStorageRootPath}"' not in helper_source
    assert 'export STORAGE_DIR="$data_root/storage"' not in helper_source
    assert 'export NGINX_PROTECTED_MEDIA_URL="${envNginxProtectedMediaUrl}"' not in helper_source
    assert "PROTECTED_MEDIA_ROOT=${runtimeStorageRootPath}" not in source
    assert "LX_ANNOTATE_STREAMABLE_VIDEO_ROOT=${runtimeStreamableVideoRootPath}" not in source
