import stat

import pytest

from lx_administration.models.vault import PreSharedKey
from lx_administration.models.vault.manager_utils import generate_ansible_key


def test_generate_ansible_key_writes_a_private_file(tmp_path):
    key_path = tmp_path / "vault.key"

    generate_ansible_key(key_path)

    assert key_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600


def test_generate_psk_writes_a_private_file_and_directory(tmp_path):
    psk_dir = tmp_path / "psks"

    psk = PreSharedKey.generate("example", psk_dir)
    psk_path = psk.file_path

    assert psk_path.read_text(encoding="utf-8")
    assert stat.S_IMODE(psk_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(psk_dir.stat().st_mode) == 0o700


def test_generate_psk_warns_before_replacing_existing_file(tmp_path):
    psk_dir = tmp_path / "psks"
    psk_dir.mkdir()
    psk_path = psk_dir / "example.psk"
    psk_path.write_text("old", encoding="utf-8")

    with pytest.warns(UserWarning, match="PSK file already exists"):
        PreSharedKey.generate("example", str(psk_dir))

    assert psk_path.read_text(encoding="utf-8") != "old"
