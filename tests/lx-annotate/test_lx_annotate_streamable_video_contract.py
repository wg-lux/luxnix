from __future__ import annotations

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO_ROOT / "modules/nixos/services/lx-annotate-local"
RUNTIME_CONTEXT_NIX = SERVICE_DIR / "runtime-context.nix"
CONFIG_NIX = SERVICE_DIR / "config.nix"
SCRIPTS_NIX = SERVICE_DIR / "scripts.nix"
OPTIONS_NIX = SERVICE_DIR / "options/runtime.nix"
README_MD = SERVICE_DIR / "README.md"


def test_streamable_video_paths_are_first_class_runtime_derivations():
    source = RUNTIME_CONTEXT_NIX.read_text(encoding="utf-8")
    options_source = OPTIONS_NIX.read_text(encoding="utf-8")

    assert (
        'runtimeStreamableVideoRootPath = '
        '"${runtimeStorageRootPath}/streamable_videos";'
        in source
    )
    assert (
        'runtimeStreamableVideoRawRootPath = '
        '"${runtimeStreamableVideoRootPath}/raw";'
        in source
    )
    assert (
        'runtimeStreamableVideoProcessedRootPath = '
        '"${runtimeStreamableVideoRootPath}/processed";'
        in source
    )
    assert 'default = "/protected_media/";' in options_source


def test_streamable_video_directories_are_provisioned_and_migration_is_exposed():
    config_source = CONFIG_NIX.read_text(encoding="utf-8")
    scripts_source = SCRIPTS_NIX.read_text(encoding="utf-8")
    readme = README_MD.read_text(encoding="utf-8")

    assert '"d ${runtimeStreamableVideoRootPath} 0750' in config_source
    assert '"d ${runtimeStreamableVideoRawRootPath} 0750' in config_source
    assert '"d ${runtimeStreamableVideoProcessedRootPath} 0750' in config_source
    assert 'alias = "${runtimeStorageRootPath}/";' in config_source
    assert 'lx-annotate-manage migrate_media_storage "$@"' in scripts_source
    assert 'export LX_RUNTIME_ROOT="${envDataDir}"' in scripts_source
    assert 'source "${lxAnnotateRuntimeLib}"' in scripts_source
    assert "lx_annotate_export_runtime_env" in scripts_source
    assert "lx-annotate-storage-migration" in readme


def test_nginx_media_requires_application_authorization():
    source = CONFIG_NIX.read_text(encoding="utf-8")

    def location_body(path: str) -> str:
        return source.split(f'"{path}" = {{', 1)[1].split("\n                  };", 1)[0]

    # Deny legacy direct URLs even when the attacker knows a patient filename.
    legacy_media = location_body("/media/")
    assert 'return 404;' in legacy_media
    assert "alias =" not in legacy_media
    assert 'alias = "${envDataDir}/";' not in source

    # Application-approved X-Accel-Redirect responses retain the internal path.
    protected_media = location_body("/protected_media/")
    assert 'alias = "${runtimeStorageRootPath}/";' in protected_media
    assert "internal;" in protected_media
    for prefix in ("/api/media/videos/", "/endoreg-api/media/videos/"):
        video_route = location_body(prefix)
        assert 'proxyPass = "http://127.0.0.1:${toString cfg.django.port}";' in video_route
        assert "videoStreamProxyExtraConfig" in video_route


def test_optional_streamable_bind_mount_is_top_level_and_null_lazy():
    config_source = CONFIG_NIX.read_text(encoding="utf-8")

    assert "fileSystems = optionalAttrs streamableExternalStorageEnabled {" in config_source
    assert "\n        fileSystems =" not in config_source
    assert "fileSystems = mkIf streamableExternalStorageEnabled" not in config_source


def test_generic_postgres_default_is_not_nested_below_services():
    config_source = CONFIG_NIX.read_text(encoding="utf-8")

    assignment = (
        "luxnix.generic-settings.postgres.enable = "
        "mkIf (!externalPostgresConfigured) (mkDefault true);"
    )
    assert assignment in config_source
    assert f"\n        {assignment}" not in config_source


def test_streamable_migration_uses_the_deployed_system_command():
    scripts = (REPO_ROOT / "devenv/scripts.nix").read_text()
    migration_script_path = REPO_ROOT / "scripts/lx-annotate-streamable-migration.sh"
    migration_script = migration_script_path.read_text()
    module = (
        REPO_ROOT / "modules/nixos/services/lx-annotate-local/config.nix"
    ).read_text()

    command = "lx-annotate-migrate-video-streamable-storage"
    subprocess.run(["bash", "-n", migration_script_path], check=True)
    assert "scripts/lx-annotate-streamable-migration.sh" in scripts
    assert f"/run/current-system/sw/bin/{command}" in migration_script
    assert "/nix/store/" not in migration_script
    assert (
        ".venv/bin/python -m django migrate_video_streamable_storage"
        not in migration_script
    )
    assert "lx_annotate_export_wheel_service_env" not in migration_script
    assert (
        "environment.systemPackages = "
        "[ lxAnnotateMigrateVideoStreamableStorageScript ];"
    ) in module
