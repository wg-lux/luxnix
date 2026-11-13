"""Private disclosure receipts; production credentials are never used."""

from contextlib import contextmanager
import io
import json
import subprocess
import sys

import pytest

from lx_administration.storage import password_custody as custody


@pytest.fixture
def record(tmp_path):
    primary = tmp_path / "cryptroot.vault"
    primary.write_bytes(b"synthetic authenticated ciphertext")
    return primary, {
        "host": "gc-09",
        "volume": "cryptroot",
        "machine_id": "1" * 32,
        "luks_uuid": "synthetic-uuid",
        "recovery_passphrase": "synthetic password\n\x1b",
    }


def test_disclosure_only_to_terminal_after_acknowledgement(record, monkeypatch, capsys):
    primary, value = record
    output = io.StringIO()

    @contextmanager
    def terminal():
        yield io.StringIO("SAVED\n"), output

    monkeypatch.setattr(custody, "terminal", terminal)
    custody.acknowledge(primary, value)
    custody.acknowledge(primary, value)
    assert output.getvalue().count(json.dumps(value["recovery_passphrase"])) == 1
    assert "\x1b" not in output.getvalue()
    assert capsys.readouterr().out == ""
    receipt = primary.with_suffix(".acknowledged.json")
    assert receipt.stat().st_mode & 0o777 == 0o600
    assert value["recovery_passphrase"] not in receipt.read_text()


def test_unconfirmed_disclosure_preserves_ciphertext_for_retry(record, monkeypatch):
    primary, value = record
    before = primary.read_bytes()

    @contextmanager
    def terminal():
        yield io.StringIO("\n"), io.StringIO()

    monkeypatch.setattr(custody, "terminal", terminal)
    with pytest.raises(custody.CustodyError, match="not acknowledged"):
        custody.acknowledge(primary, value)
    assert primary.read_bytes() == before
    assert not primary.with_suffix(".acknowledged.json").exists()


def test_no_tty_never_discloses_to_stdout_or_stderr(record):
    primary, value = record
    program = (
        "from pathlib import Path\n"
        "from lx_administration.storage.password_custody "
        "import acknowledge, CustodyError\n"
        "try:\n"
        f"    acknowledge(Path({str(primary)!r}), {value!r})\n"
        "except CustodyError:\n"
        "    raise SystemExit(7)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        start_new_session=True,
        input=b"SAVED\n",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 7
    assert result.stdout == result.stderr == b""
    assert not primary.with_suffix(".acknowledged.json").exists()
