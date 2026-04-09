from __future__ import annotations

from pathlib import Path


DEFAULT_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/default.nix"
)
CONFIG_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/config.nix"
)
SCRIPTS_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix"
)
README_MD = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/README.md"
)


def test_streamable_video_paths_are_first_class_runtime_derivations():
    source = DEFAULT_NIX.read_text(encoding="utf-8")

    assert 'runtimeStreamableVideoRootPath = "${runtimeStorageRootPath}/streamable_videos";' in source
    assert 'runtimeStreamableVideoRawRootPath = "${runtimeStreamableVideoRootPath}/raw";' in source
    assert (
        'runtimeStreamableVideoProcessedRootPath = "${runtimeStreamableVideoRootPath}/processed";'
        in source
    )
    assert "envProtectedMediaRoot = runtimeStorageRootPath;" in source
    assert 'envNginxProtectedMediaUrl = "/protected_media/";' in source
    assert "envStreamableVideoRoot = runtimeStreamableVideoRootPath;" in source
    assert "envStreamableVideoRawRoot = runtimeStreamableVideoRawRootPath;" in source
    assert (
        "envStreamableVideoProcessedRoot = runtimeStreamableVideoProcessedRootPath;"
        in source
    )


def test_streamable_video_directories_are_provisioned_and_migration_is_exposed():
    config_source = CONFIG_NIX.read_text(encoding="utf-8")
    scripts_source = SCRIPTS_NIX.read_text(encoding="utf-8")
    readme = README_MD.read_text(encoding="utf-8")

    assert '"d ${runtimeStreamableVideoRootPath} 0750' in config_source
    assert '"d ${runtimeStreamableVideoRawRootPath} 0750' in config_source
    assert '"d ${runtimeStreamableVideoProcessedRootPath} 0750' in config_source
    assert "systemd.services.lx-annotate-video-streamable-migration" in config_source
    assert 'alias = "${envProtectedMediaRoot}/";' in config_source
    assert "migrate_video_streamable_storage" in scripts_source
    assert 'source "${lxAnnotateRuntimeLib}"' in scripts_source
    assert "lx_annotate_export_runtime_env" in scripts_source
    assert "lx-annotate-video-streamable-migration" in readme
