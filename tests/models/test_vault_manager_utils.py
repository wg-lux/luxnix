from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from lx_administration.models.vault.manager_utils import (
    _assert_unique_list,
    _get_by_name,
    _get_by_target_name,
    _is_valid,
    ensure_local_vault_key,
    generate_ansible_key,
    generate_secret_dir_path,
)


def test_ensure_local_vault_key_expands_home_before_checking(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    existing_key = tmp_path / ".lxv.key"
    existing_key.write_text("existing", encoding="utf-8")

    resolved_key = ensure_local_vault_key("~/.lxv.key")

    assert resolved_key == existing_key
    assert existing_key.read_text(encoding="utf-8") == "existing"


def test_generate_ansible_key_refuses_to_overwrite(tmp_path):
    existing_key = tmp_path / "vault.key"
    existing_key.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        generate_ansible_key(existing_key)

    assert existing_key.read_text(encoding="utf-8") == "existing"


@pytest.mark.parametrize("attribute", ["owner_type", "secret_type"])
def test_generate_secret_dir_rejects_unknown_types(tmp_path, attribute):
    arguments = {
        "name": "example",
        "vault_dir": tmp_path,
        "owner_type": "local",
        "secret_type": "password",
    }
    arguments[attribute] = "unknown"

    with pytest.raises(ValueError, match=f"Invalid {attribute}"):
        generate_secret_dir_path(**arguments)


def test_model_lookup_helpers_share_unique_match_behavior():
    first = SimpleNamespace(name="first", target_name="SCRT_first")
    second = SimpleNamespace(name="second", target_name="SCRT_second")

    assert _get_by_name([first, second], "first") is first
    assert _get_by_target_name([first, second], "SCRT_second") is second
    assert _get_by_name([first, second], "missing") is None


def test_model_lookup_rejects_ambiguous_matches():
    duplicate = SimpleNamespace(name="duplicate")

    with pytest.raises(
        ValueError,
        match="Found 2 objects with name='duplicate'; expected one",
    ):
        _get_by_name([duplicate, duplicate], "duplicate")


def test_unique_list_reports_duplicate_values():
    with pytest.raises(ValueError, match=r"duplicates: \['same'\]"):
        _assert_unique_list(["same", "same", "other"])


def test_unique_list_has_no_success_payload():
    assert _assert_unique_list(["first", "second"]) is None


def test_validity_uses_last_update_as_window_start():
    created = datetime(2026, 1, 1)
    updated = datetime(2026, 2, 1)

    assert _is_valid(
        timedelta(days=30),
        created,
        updated,
        now=datetime(2026, 3, 1),
    )
    assert not _is_valid(
        timedelta(days=30),
        created,
        updated,
        now=datetime(2026, 3, 4),
    )


def test_validity_rejects_future_reference_time():
    assert not _is_valid(
        timedelta(days=30),
        datetime(2026, 2, 1),
        None,
        now=datetime(2026, 1, 1),
    )
