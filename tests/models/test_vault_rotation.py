from unittest.mock import MagicMock, patch
from pathlib import Path
import runpy

import pytest

from lx_administration.models.vault import Secret, Vault


def secret(name):
    return Secret(
        name=name,
        file="unused",
        owner_type="local",
        template_name="admin@client",
        target_name=name,
    )


@pytest.mark.parametrize(
    "name", ["admin@client_password", "admin@client_password_hash"]
)
def test_generic_rotation_refuses_paired_login_credentials_before_writing(name):
    vault = Vault(
        secrets=[secret("admin@client_password"), secret("admin@client_password_hash")]
    )
    with patch.object(Secret, "update_file_encryption") as encrypt:
        with pytest.raises(ValueError, match="Paired password/hash"):
            vault.update_secret_value(name, "replacement")
    encrypt.assert_not_called()
    assert all(entry.value is None for entry in vault.secrets)


@pytest.mark.parametrize("fails", [True, False])
def test_rotation_clears_plaintext_and_dates_only_successful_updates(fails):
    entry = secret("standalone")
    vault = Vault(secrets=[entry])
    with (
        patch.object(
            Secret,
            "update_file_encryption",
            side_effect=RuntimeError("failed") if fails else None,
        ),
        patch.object(Vault, "save_to_file") as save,
    ):
        if fails:
            with pytest.raises(RuntimeError):
                vault.update_secret_value(entry.name, "replacement")
            save.assert_not_called()
            assert entry.updated is None
        else:
            vault.update_secret_value(entry.name, "replacement")
            save.assert_called_once()
            assert entry.updated is not None
    assert entry.value is None


@pytest.mark.parametrize(
    "argument",
    [["--custom-value", "SENSITIVE_INPUT"], ["--custom-value=SENSITIVE_INPUT"]],
)
def test_cli_rejects_argument_secret_without_echoing_it(argument, capsys):
    cli = runpy.run_path(
        str(Path(__file__).resolve().parents[2] / "scripts/update_secret.py")
    )
    with pytest.raises(SystemExit):
        cli["parse_args"](["--secret-name", "example", *argument])
    output = capsys.readouterr()
    assert "SENSITIVE_INPUT" not in output.err + output.out
    assert "--prompt-value" in output.err


def test_cli_default_generation_produces_usable_secret_without_printing_it(
    monkeypatch, capsys
):
    script = Path(__file__).resolve().parents[2] / "scripts/update_secret.py"
    monkeypatch.setattr("sys.argv", [str(script), "--secret-name", "standalone"])
    vault = MagicMock()
    with patch.object(Vault, "load_dir", return_value=vault):
        runpy.run_path(str(script), run_name="__main__")
    name, value = vault.update_secret_value.call_args.args
    assert name == "standalone"
    assert len(value) == 16
    assert any(char.isupper() for char in value)
    assert any(char.islower() for char in value)
    assert any(char.isdigit() for char in value)
    output = capsys.readouterr()
    assert value not in output.out + output.err
