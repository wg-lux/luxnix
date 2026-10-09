import pytest

from lx_administration.models.vault import AnsibleCfg
from lx_administration.models.vault.ansible_cfg import AnsibleCfgDefaults


def test_default_config_round_trips_without_none_values(tmp_path):
    config_path = tmp_path / "nested/ansible.cfg"

    AnsibleCfg().save_to_file(config_path)
    loaded = AnsibleCfg.from_file(config_path)

    assert loaded == AnsibleCfg()
    content = config_path.read_text(encoding="utf-8")
    assert "vault_identity_list" not in content
    assert "private_key_file" not in content


def test_from_file_rejects_missing_config(tmp_path):
    missing = tmp_path / "missing.cfg"

    with pytest.raises(FileNotFoundError, match=f"Ansible config not found: {missing}"):
        AnsibleCfg.from_file(missing)


def test_vault_identity_helpers_trim_and_drop_missing_files(tmp_path):
    existing = tmp_path / "client.psk"
    existing.write_text("key", encoding="utf-8")
    missing = tmp_path / "missing.psk"
    defaults = AnsibleCfgDefaults(
        vault_identity_list=f" client@{existing}, missing@{missing}, "
    )

    assert defaults.get_vid_dict() == {
        "client": str(existing),
        "missing": str(missing),
    }
    with pytest.warns(UserWarning, match="missing files"):
        defaults.drop_missing_vid()

    assert defaults.vault_identity_list == f"client@{existing}"
