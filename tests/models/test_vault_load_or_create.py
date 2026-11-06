from unittest.mock import MagicMock, patch

from lx_administration.models.vault import Vault


def test_load_or_create_keeps_requested_paths(tmp_path):
    vault_dir = tmp_path / "vault"
    vault_key = tmp_path / "vault.key"

    with (
        patch.object(Vault, "save_to_file") as save_to_file,
        patch(
            "lx_administration.models.vault.manager.get_logger",
            return_value=MagicMock(),
        ),
    ):
        vault = Vault.load_or_create(str(vault_dir), str(vault_key))

    assert vault.dir == str(vault_dir)
    assert vault.key == str(vault_key)
    save_to_file.assert_called_once_with(str(vault_dir / "vault.yml"))
