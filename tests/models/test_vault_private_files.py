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


@pytest.mark.parametrize("operation", ["master", "host", "read"])
def test_vault_keys_require_encrypted_storage(tmp_path, monkeypatch, operation):
    from lx_administration import secret_storage
    from lx_administration.models.vault.secret import _read_key

    def denied_probe(*command):
        return {
            "swapon": {"swapdevices": []},
            "findmnt": {"filesystems": [{"fstype": "ext4", "source": "/dev/test"}]},
            "lsblk": {"blockdevices": [{"type": "disk"}]},
        }[command[0]]

    monkeypatch.setattr(secret_storage, "_probe", denied_probe)
    key_path = tmp_path / "key"
    if operation == "read":
        key_path.write_text("synthetic-test-key")
        key_path.chmod(0o600)
        with pytest.raises(ValueError, match="encrypted devices"):
            _read_key(key_path)
        assert key_path.read_text() == "synthetic-test-key"
    elif operation == "master":
        with pytest.raises(ValueError, match="encrypted devices"):
            generate_ansible_key(key_path)
        assert not key_path.exists()
    else:
        with pytest.raises(ValueError, match="encrypted devices"):
            PreSharedKey.generate("example", tmp_path / "psks")
        assert not list((tmp_path / "psks").iterdir())
