from datetime import timedelta
from unittest.mock import MagicMock, patch

from lx_administration.models.vault import PreSharedKey, Secret, SecretTemplate, Vault


def test_load_dir_materializes_nested_vault_models(tmp_path):
    vault_file = tmp_path / "vault.yml"
    vault_file.write_text(
        f"""
dir: {tmp_path}
key: {tmp_path / "vault.key"}
secret_templates:
  - name: database-role
    owner_type: roles
    secret_names:
      - database
secrets:
  - name: database
    file: {tmp_path / "database.secret"}
    owner_type: roles
    template_name: database-role
    target_name: SCRT_database
pre_shared_keys:
  - name: client
    file: {tmp_path / "client.psk"}
    validity: P7D
""".lstrip(),
        encoding="utf-8",
    )

    with patch(
        "lx_administration.models.vault.manager.get_logger",
        return_value=MagicMock(),
    ):
        vault = Vault.load_dir(str(tmp_path), str(tmp_path / "vault.key"))

    assert isinstance(vault.secret_templates[0], SecretTemplate)
    assert isinstance(vault.secrets[0], Secret)
    assert isinstance(vault.pre_shared_keys[0], PreSharedKey)
    assert vault.pre_shared_keys[0].validity == timedelta(days=7)
