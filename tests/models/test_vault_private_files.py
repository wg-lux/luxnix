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


def test_generate_psk_never_replaces_existing_file(tmp_path):
    psk_dir = tmp_path / "psks"
    psk_dir.mkdir()
    psk_path = psk_dir / "example.psk"
    psk_path.write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match="PSK already exists"):
        PreSharedKey.generate("example", str(psk_dir))

    assert psk_path.read_text(encoding="utf-8") == "old"


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


def test_psk_exclusive_publication_preserves_a_concurrent_key(tmp_path, monkeypatch):
    from lx_administration.utils import file_operations

    directory = tmp_path / "psks"
    target = directory / "example.psk"
    original_link = file_operations.os.link

    def concurrent_create(source, destination):
        target.write_text("synthetic-concurrent-key")
        return original_link(source, destination)

    monkeypatch.setattr(file_operations.os, "link", concurrent_create)
    with pytest.raises(FileExistsError):
        PreSharedKey.generate("example", directory)
    assert target.read_text() == "synthetic-concurrent-key"
    assert list(directory.iterdir()) == [target]


def test_psk_creation_rejects_dangling_symlink_and_traversal(tmp_path):
    directory = tmp_path / "psks"
    directory.mkdir()
    link = directory / "example.psk"
    victim = tmp_path / "victim"
    link.symlink_to(victim)
    with pytest.raises(FileExistsError):
        PreSharedKey.generate("example", directory)
    assert link.is_symlink() and not victim.exists()
    with pytest.raises(ValueError, match="name"):
        PreSharedKey.generate("../victim", directory)
    assert not victim.exists()


def test_psk_missing_metadata_preserves_orphan_key(tmp_path):
    from lx_administration.models.vault import Vault

    directory = tmp_path / "psk"
    directory.mkdir()
    target = directory / "example.psk"
    target.write_text("synthetic-orphan-key")
    vault = Vault(dir=str(tmp_path))
    with pytest.raises(FileExistsError):
        vault.get_or_create_psk("example")
    assert target.read_text() == "synthetic-orphan-key"
    assert vault.pre_shared_keys == []


@pytest.mark.parametrize("unsafe", ["missing", "empty", "public", "symlink"])
def test_psk_existing_metadata_never_authorizes_regeneration(tmp_path, unsafe):
    from lx_administration.models.vault import Vault

    directory = tmp_path / "psk"
    directory.mkdir()
    target = directory / "example.psk"
    if unsafe == "symlink":
        target.symlink_to(tmp_path / "missing")
    elif unsafe != "missing":
        target.write_text("" if unsafe == "empty" else "synthetic-existing-key")
        target.chmod(0o644 if unsafe == "public" else 0o600)
    metadata = PreSharedKey(name="example", file=str(target))
    vault = Vault(dir=str(tmp_path), pre_shared_keys=[metadata])
    with pytest.raises((FileNotFoundError, ValueError)):
        vault.get_or_create_psk("example")
    assert vault.pre_shared_keys == [metadata]
    if unsafe == "missing":
        assert not target.exists()
    elif unsafe == "empty":
        assert target.read_text() == ""
    elif unsafe == "public":
        assert target.read_text() == "synthetic-existing-key"
    else:
        assert target.is_symlink()


def test_master_key_exclusive_publication_preserves_concurrent_key(
    tmp_path, monkeypatch
):
    from lx_administration.utils import file_operations

    target = tmp_path / "vault.key"
    original_link = file_operations.os.link

    def concurrent_create(source, destination):
        target.write_text("synthetic-concurrent-master")
        return original_link(source, destination)

    monkeypatch.setattr(file_operations.os, "link", concurrent_create)
    with pytest.raises(FileExistsError):
        generate_ansible_key(target)
    assert target.read_text() == "synthetic-concurrent-master"
    assert list(tmp_path.iterdir()) == [target]
