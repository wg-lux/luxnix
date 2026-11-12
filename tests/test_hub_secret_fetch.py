"""Last-known-good hub secret delivery: outages keep, bad answers never deploy."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/vault/fetch_hub_secret.py"
CLASSIFIER = ROOT / "scripts/vault/classify-auth-error.sh"
VALUE = "fetched-value"

FAKE_CLI = """#!/bin/sh
# Stand-in for the Vault-compatible client; behaviour is selected by the test.
case "$FAKE_MODE" in
  ok) printf '%s' "$FAKE_RESPONSE" ;;
  sealed) echo "Code: 503. Errors: * $FAKE_PRODUCT is sealed" >&2; exit 2 ;;
  unreachable) echo 'dial tcp 10.0.0.1:8200: connect: connection refused' >&2; exit 2 ;;
  denied) echo 'Code: 403. Errors: * permission denied' >&2; exit 2 ;;
  missing) echo 'No value found at kv/data/shared/example' >&2; exit 2 ;;
  garbage) printf 'not json' ;;
esac
"""


def response(version=3, value=VALUE, field="value"):
    return json.dumps({"data": {"data": {field: value}, "metadata": {"version": version}}})


@pytest.fixture
def site(tmp_path):
    cli = tmp_path / "vault"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    # The module installs the classifier as an executable; mirror that here.
    classifier = tmp_path / "classify"
    classifier.write_text(f'#!/bin/sh\nexec bash {CLASSIFIER} "$@"\n')
    classifier.chmod(0o755)
    target = tmp_path / ".secret.tmp"
    target.touch(mode=0o600)
    return tmp_path


def run(site, mode, *extra, token="token", product="Vault", **reply):
    environment = {
        "PATH": os.environ["PATH"],
        "FAKE_MODE": mode,
        "FAKE_PRODUCT": product,
        "FAKE_RESPONSE": response(**reply),
    }
    if token:
        environment["VAULT_TOKEN"] = token
    return subprocess.run(
        [
            sys.executable, str(HELPER),
            "--name", "example",
            "--kv-path", "kv/shared/example",
            "--field", "value",
            "--target", str(site / ".secret.tmp"),
            "--previous", str(site / "secret"),
            "--state-dir", str(site / "state"),
            "--cli", str(site / "vault"),
            "--classifier", str(site / "classify"),
            *extra,
        ],
        env=environment, capture_output=True, text=True, check=False,
    )


def state(site):
    return json.loads((site / "state/example.json").read_text())


def test_fresh_value_is_written_and_only_metadata_is_recorded(site):
    result = run(site, "ok")
    assert result.returncode == 0, result.stderr
    assert (site / ".secret.tmp").read_text() == VALUE
    assert stat.S_IMODE((site / ".secret.tmp").stat().st_mode) == 0o600
    recorded = state(site)
    assert recorded["version"] == 3 and recorded["status"] == "current"
    assert VALUE not in json.dumps(recorded)
    assert VALUE not in result.stdout + result.stderr


@pytest.mark.parametrize("product", ["Vault", "OpenBao"])
@pytest.mark.parametrize("mode", ["sealed", "unreachable"])
def test_outage_keeps_the_deployed_value_only_when_tolerated(site, mode, product):
    (site / "secret").write_text("deployed")
    strict = run(site, mode, product=product)
    assert strict.returncode == 1 and "hub unavailable" in strict.stderr
    assert (site / ".secret.tmp").read_text() == ""

    tolerant = run(site, mode, "--tolerate-outage", product=product)
    assert tolerant.returncode == 0, tolerant.stderr
    assert (site / ".secret.tmp").read_text() == "deployed"
    assert "BLOCKER" in tolerant.stderr
    assert state(site)["status"] == "degraded"


def test_missing_runtime_token_counts_as_outage_without_calling_the_hub(site):
    (site / "secret").write_text("deployed")
    result = run(site, "ok", "--tolerate-outage", token=None)
    assert result.returncode == 0
    assert (site / ".secret.tmp").read_text() == "deployed"
    assert state(site)["reason"] == "auth-unavailable"


def test_first_provisioning_fails_closed_during_an_outage(site):
    result = run(site, "unreachable", "--tolerate-outage")
    assert result.returncode == 1
    assert (site / ".secret.tmp").read_text() == ""


@pytest.mark.parametrize("mode", ["denied", "missing", "garbage"])
def test_answers_from_the_hub_are_never_replaced_by_the_cache(site, mode):
    (site / "secret").write_text("deployed")
    result = run(site, mode, "--tolerate-outage")
    assert result.returncode == 1
    assert (site / ".secret.tmp").read_text() == ""


def test_older_version_is_rejected_as_a_stale_answer(site):
    assert run(site, "ok", version=5).returncode == 0
    (site / "secret").write_text(VALUE)
    stale = run(site, "ok", "--tolerate-outage", version=4, value="rolled-back")
    assert stale.returncode == 1
    assert "older than accepted version 5" in stale.stderr
    assert state(site)["version"] == 5
    assert run(site, "ok", version=6, value="rotated").returncode == 0
    assert (site / ".secret.tmp").read_text() == "rotated"


@pytest.mark.parametrize("value", ["", "\n", "   "])
def test_empty_values_are_rejected(site, value):
    assert run(site, "ok", value=value).returncode == 1


def test_newlines_are_stripped_only_on_request(site):
    assert run(site, "ok", value="a\nb\n").returncode == 0
    assert (site / ".secret.tmp").read_text() == "a\nb\n"
    assert run(site, "ok", "--strip-newlines", value="a\nb\n").returncode == 0
    assert (site / ".secret.tmp").read_text() == "ab"


def test_optional_secret_becomes_empty_instead_of_failing(site):
    result = run(site, "denied", "--empty-when-unavailable")
    assert result.returncode == 0
    assert (site / ".secret.tmp").read_text() == ""
    (site / "secret").write_text("deployed")
    kept = run(site, "unreachable", "--tolerate-outage", "--empty-when-unavailable")
    assert kept.returncode == 0
    assert (site / ".secret.tmp").read_text() == "deployed"


def test_target_symlink_is_refused(site):
    (site / ".secret.tmp").unlink()
    (site / "elsewhere").touch()
    (site / ".secret.tmp").symlink_to(site / "elsewhere")
    result = run(site, "ok")
    assert result.returncode != 0
    assert (site / "elsewhere").read_text() == ""


@pytest.mark.parametrize("path", ["kv", "../kv/x", "kv/../x", "kv/a b"])
def test_malformed_kv_paths_are_usage_errors(site, path):
    result = subprocess.run(
        [sys.executable, str(HELPER), "--name", "x", "--kv-path", path, "--field", "f",
         "--target", str(site / ".secret.tmp"), "--state-dir", str(site / "state")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
