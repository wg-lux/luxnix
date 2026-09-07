from datetime import UTC, datetime, timedelta
from pathlib import Path

from lx_administration.models.vault import PreSharedKey, Vault


def test_pre_shared_key_uses_pydantic_serialization_modes():
    psk = PreSharedKey(
        name="client@example",
        file="/tmp/client.psk",
        created=datetime(2026, 8, 4, 12, 30),
        validity=timedelta(days=30),
    )

    assert psk.model_dump()["validity"] == timedelta(days=30)
    assert psk.model_dump(mode="json", exclude_none=True) == {
        "name": "client@example",
        "file": "/tmp/client.psk",
        "created": "2026-08-04T12:30:00",
        "validity": "P30D",
        "vault_id_prefix": "client--example",
    }


def test_vault_json_dump_serializes_nested_pre_shared_keys():
    psk = PreSharedKey(
        name="client",
        file="/tmp/client.psk",
        validity=timedelta(days=30),
    )

    dumped = Vault(pre_shared_keys=[psk]).model_dump(mode="json", exclude_none=True)

    assert dumped["pre_shared_keys"] == [
        {
            "name": "client",
            "file": "/tmp/client.psk",
            "validity": "P30D",
            "vault_id_prefix": "client",
        }
    ]


def test_pre_shared_key_uses_name_for_empty_vault_id_prefix():
    psk = PreSharedKey(
        name="client@example",
        file="/tmp/client.psk",
        vault_id_prefix=None,
    )

    assert psk.vault_id_prefix == "client--example"


def test_pre_shared_key_normalizes_persisted_input():
    psk = PreSharedKey.model_validate(
        {
            "name": "client@example",
            "file": Path("/tmp/client.psk"),
            "created": "2026-08-04T12:30:00Z",
            "updated": "invalid",
            "validity": "7 days",
        }
    )

    assert psk.file == "/tmp/client.psk"
    assert psk.created == datetime(2026, 8, 4, 12, 30, tzinfo=UTC)
    assert psk.updated is None
    assert psk.validity == timedelta(days=7)
    assert psk.vault_id_prefix == "client--example"


def test_pre_shared_key_falls_back_for_invalid_validity():
    psk = PreSharedKey(
        name="client",
        file="/tmp/client.psk",
        validity="invalid",
    )

    assert psk.validity == timedelta(days=30)
