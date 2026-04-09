from __future__ import annotations

from pathlib import Path


SCRIPTS_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix"
)


def test_lx_annotate_scripts_export_protected_storage_contract():
    source = SCRIPTS_NIX.read_text(encoding="utf-8")

    assert 'export NGINX_PROTECTED_MEDIA_URL="${envNginxProtectedMediaUrl}"' in source
    assert 'export PROTECTED_MEDIA_ROOT="${envProtectedMediaRoot}"' in source
    assert 'export LX_ANNOTATE_STREAMABLE_VIDEO_ROOT="${envStreamableVideoRoot}"' in source
    assert 'export LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT="${envStreamableVideoRawRoot}"' in source
    assert (
        'export LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT="${envStreamableVideoProcessedRoot}"'
        in source
    )
