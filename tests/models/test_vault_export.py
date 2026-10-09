from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest

from lx_administration.models.ansible import AnsibleInventory
from lx_administration.models.vault import PreSharedKey, Vault
from lx_administration.utils.file_operations import advisory_file_lock


def test_export_secrets_by_client_reencrypts_each_secret(tmp_path):
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.get_hostnames.return_value = ["client", None]
    vault = Vault(dir=str(tmp_path), inventory=inventory)

    psk_file = tmp_path / "client.psk"
    psk_file.write_text("pre-shared-key", encoding="utf-8")
    psk = PreSharedKey(name="client", file=str(psk_file))

    secret = MagicMock()
    secret.name = "database-password"
    secret.target_name = "database-password.yml"
    secret.create_re_encrypted_file.side_effect = lambda target, *args: Path(
        target
    ).write_text("encrypted")
    logger = MagicMock()

    with (
        patch.object(Vault, "get_client_psk", return_value=psk) as get_client_psk,
        patch.object(Vault, "get_host_secrets", return_value=[secret]) as get_secrets,
    ):
        vault.export_secrets_by_client(logger=logger)

    get_client_psk.assert_called_once_with("client", logger)
    get_secrets.assert_called_once_with("client", logger)
    target, key, exported_vault = secret.create_re_encrypted_file.call_args.args
    assert Path(target).name == "database-password.yml"
    assert key == str(psk_file)
    assert exported_vault is vault
    assert (tmp_path / "deploy/client/database-password.yml").read_text() == "encrypted"
    assert (tmp_path / "deploy").stat().st_mode & 0o777 == 0o700
    assert not list(tmp_path.glob(".export-*/"))


def test_export_requires_inventory_before_replacing_deploy_directory(tmp_path):
    deploy_dir = tmp_path / "deploy"
    deploy_dir.mkdir()
    marker = deploy_dir / "existing-secret"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="Inventory must be loaded"):
        Vault(dir=str(tmp_path)).export_secrets_by_client(logger=MagicMock())

    assert marker.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    "failure",
    ["missing-psk", "missing-file", "empty-psk", "encrypt", "duplicate", "traversal"],
)
def test_failed_export_preserves_previous_bundle(tmp_path, failure):
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.get_hostnames.return_value = ["client"]
    vault = Vault(dir=str(tmp_path), inventory=inventory)
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "previous").write_text("old encrypted bundle")
    psk_file = tmp_path / "client.psk"
    if failure != "missing-file":
        psk_file.write_text("" if failure == "empty-psk" else "test key")
    psk = (
        None
        if failure == "missing-psk"
        else PreSharedKey(name="client", file=str(psk_file))
    )
    secret = MagicMock()
    secret.target_name = "../escaped" if failure == "traversal" else "secret"
    secret.create_re_encrypted_file.side_effect = (
        RuntimeError("SENSITIVE_PROVIDER_OUTPUT")
        if failure == "encrypt"
        else lambda target, *args: Path(target).write_text("encrypted")
    )
    with (
        patch.object(Vault, "get_client_psk", return_value=psk),
        patch.object(
            Vault,
            "get_host_secrets",
            return_value=[secret, secret] if failure == "duplicate" else [secret],
        ),
        pytest.raises((ValueError, RuntimeError)) as error,
    ):
        vault.export_secrets_by_client(logger=MagicMock())
    assert "SENSITIVE_PROVIDER_OUTPUT" not in str(error.value)
    assert (deploy / "previous").read_text() == "old encrypted bundle"
    assert not list(tmp_path.glob(".export-*/"))


def test_failed_publication_restores_previous_export(tmp_path, monkeypatch):
    inventory = MagicMock(spec=AnsibleInventory)
    inventory.get_hostnames.return_value = []
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "previous").write_text("old encrypted bundle")
    rename = Path.rename

    def fail_publication(source, target):
        if source.name == "deploy" and source.parent.name.startswith(".export-"):
            raise OSError("publication failed")
        return rename(source, target)

    monkeypatch.setattr(Path, "rename", fail_publication)
    with pytest.raises(OSError, match="publication failed"):
        Vault(dir=str(tmp_path), inventory=inventory).export_secrets_by_client(
            logger=MagicMock()
        )
    assert (deploy / "previous").read_text() == "old encrypted bundle"
    assert not (tmp_path / ".deploy-previous").exists()


@pytest.mark.parametrize("blocker", ["interrupted", "concurrent"])
def test_export_recovery_and_concurrency_guards_preserve_evidence(tmp_path, blocker):
    inventory = MagicMock(spec=AnsibleInventory)
    vault = Vault(dir=str(tmp_path), inventory=inventory)
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "previous").write_text("old encrypted bundle")
    if blocker == "interrupted":
        previous = tmp_path / ".deploy-previous"
        previous.mkdir()
        (previous / "evidence").write_text("recovery evidence")
        with pytest.raises(ValueError, match="Interrupted export"):
            vault.export_secrets_by_client(logger=MagicMock())
        assert (previous / "evidence").read_text() == "recovery evidence"
    else:
        with advisory_file_lock(lock_path=tmp_path / ".export.lock"):
            with pytest.raises(TimeoutError):
                vault.export_secrets_by_client(logger=MagicMock())
    assert (deploy / "previous").read_text() == "old encrypted bundle"
    inventory.get_hostnames.assert_not_called()
