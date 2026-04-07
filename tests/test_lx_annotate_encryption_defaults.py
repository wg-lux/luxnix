from __future__ import annotations

from pathlib import Path


SCRIPTS_NIX = Path(
    "/home/admin/luxnix/modules/nixos/services/lx-annotate-local/scripts.nix"
)


def test_lx_annotate_scripts_export_encrypted_storage_by_default():
    source = SCRIPTS_NIX.read_text(encoding="utf-8")

    assert 'export LX_ANNOTATE_USE_ENCRYPTED_STORAGE="1"' in source
    assert "LX_ANNOTATE_USE_ENCRYPTED_STORAGE=1" in source
