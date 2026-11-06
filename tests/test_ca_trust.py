"""CA trust verification rejects distrusted roots and repairs mutable certifi bundles."""

import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/nixos/luxnix/ca-trust"


def _pem(kind: str, der: bytes) -> str:
    return f"-----BEGIN {kind}-----\n{base64.b64encode(der).decode()}\n-----END {kind}-----\n"


def _der(marker: bytes) -> bytes:
    return bytes([0x30, len(marker)]) + marker


def _entry(label: str, der: bytes, *, rejected: bool = False) -> str:
    # Mirrors the nss-cacert ca-bundle.crt layout produced by buildcatrust.
    aux = bytes([0x30, 0x02, 0x05, 0x00])
    if rejected:
        return f"{label}\nTraditional PEM block omitted.\nRejected for:\n  - serverAuth\n{_pem('TRUSTED CERTIFICATE', der + aux)}\n"
    return f"{label}\n{_pem('CERTIFICATE', der)}\nTrusted for:\n  - serverAuth\n{_pem('TRUSTED CERTIFICATE', der + aux)}\n"


def _verify(tmp_path: Path, bundle_text: str, *labels: str) -> subprocess.CompletedProcess:
    source = tmp_path / "source.crt"
    source.write_text("## header\n\n" + _entry("Good Root", _der(b"good")) + _entry("Bad Root", _der(b"bad")))
    bundle = tmp_path / "bundle.crt"
    bundle.write_text(bundle_text)
    command = [sys.executable, "-I", str(MODULE / "verify-bundle.py"), "--source", str(source), "--bundle", str(bundle)]
    for label in labels:
        command += ["--label", label]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_verifier_accepts_bundle_without_distrusted_root(tmp_path):
    result = _verify(tmp_path, f"Good Root\n{_pem('CERTIFICATE', _der(b'good'))}", "Bad Root")
    assert result.returncode == 0, result.stderr


def test_verifier_rejects_distrusted_root_in_any_block_form(tmp_path):
    plain = _verify(tmp_path, f"Renamed\n{_pem('CERTIFICATE', _der(b'bad'))}", "Bad Root")
    assert plain.returncode == 1 and "Bad Root" in plain.stderr
    # Blacklisted roots stay as OpenSSL "rejected" blocks that other parsers trust.
    rejected = _verify(tmp_path, _entry("Bad Root", _der(b"bad"), rejected=True), "Bad Root")
    assert rejected.returncode == 1 and "Bad Root" in rejected.stderr


def test_verifier_rejects_label_missing_from_source(tmp_path):
    result = _verify(tmp_path, "", "Retired Root")
    assert result.returncode == 1 and "Retired Root" in result.stderr


def _repair(*args: str | Path) -> subprocess.CompletedProcess:
    command = [sys.executable, "-I", str(MODULE / "repair.py"), *map(str, args)]
    return subprocess.run(command, capture_output=True, text=True, check=False)


def test_repair_relinks_certifi_and_vendored_bundles(tmp_path):
    bundle = tmp_path / "system.crt"
    bundle.write_text("system")
    venv = tmp_path / "venv"
    site = venv / "lib/python3.12/site-packages"
    stale = [site / "certifi/cacert.pem", site / "pip/_vendor/certifi/cacert.pem"]
    for pem in stale:
        pem.parent.mkdir(parents=True)
        pem.write_text("bundled")
    (venv / "pyvenv.cfg").write_text("version = 3.12.0\n")

    check = _repair("--bundle", bundle, "--check", venv)
    assert check.returncode == 1
    assert all(str(pem) in check.stderr for pem in stale)
    assert all(not pem.is_symlink() for pem in stale)

    assert _repair("--bundle", bundle, venv).returncode == 0
    assert all(pem.resolve() == bundle.resolve() for pem in stale)
    assert _repair("--bundle", bundle, "--check", venv).returncode == 0


def test_repair_rejects_non_virtualenv(tmp_path):
    bundle = tmp_path / "system.crt"
    bundle.write_text("system")
    result = _repair("--bundle", bundle, tmp_path)
    assert result.returncode == 1 and "not a Python virtual environment" in result.stderr
