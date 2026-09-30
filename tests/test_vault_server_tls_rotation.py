from __future__ import annotations

import grp
import os
from pathlib import Path
import shutil
import stat
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/vault/maintain-server-tls.sh"
AUTH_CLASSIFIER = REPO_ROOT / "scripts/vault/classify-auth-error.sh"


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _fingerprint(certificate: Path) -> str:
    result = subprocess.run(
        ["openssl", "x509", "-in", certificate, "-noout", "-fingerprint", "-sha256"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _classify_auth_error(tmp_path: Path, error: str) -> str:
    error_file = tmp_path / "vault.stderr"
    error_file.write_text(error)
    result = subprocess.run(
        ["bash", str(AUTH_CLASSIFIER), str(error_file)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_vault_auth_errors_have_distinct_safe_states(tmp_path: Path) -> None:
    cases = [
        (
            "tls: failed to verify certificate: "
            "x509: certificate signed by unknown authority",
            "tls-trust-failed",
        ),
        (
            "Error making API request.\nCode: 503. Errors:\n* Vault is sealed",
            "vault-sealed",
        ),
        (
            "dial tcp 172.16.255.22:8200: connect: connection refused",
            "vault-unreachable",
        ),
        ("Code: 403. Errors:\n* permission denied", "auth-rejected"),
        ("an unexpected Vault response without credentials", "vault-error"),
    ]

    for error, expected in cases:
        assert _classify_auth_error(tmp_path, error) == expected


def test_vault_leaf_rotation_preserves_ca_and_rejects_ca_replacement(
    tmp_path: Path,
) -> None:
    state = tmp_path / "vault-pki"
    ca_cert = state / "ca.crt"
    ca_key = state / "ca.key"
    server_cert = state / "server.crt"
    server_key = state / "server.key"
    marker = tmp_path / "leaf-rotated"
    common_args = (
        "--state-dir",
        str(state),
        "--ca-cert",
        str(ca_cert),
        "--ca-key",
        str(ca_key),
        "--server-cert",
        str(server_cert),
        "--server-key",
        str(server_key),
        "--read-group",
        grp.getgrgid(os.getgid()).gr_name,
        "--ca-common-name",
        "Test Vault CA",
        "--server-common-name",
        "vault.endo-reg.net",
        "--ca-validity-days",
        "365",
        "--leaf-validity-days",
        "30",
        "--renew-before-days",
        "7",
        "--dns-name",
        "vault.endo-reg.net",
        "--dns-name",
        "gs-02.intern",
        "--ip-address",
        "172.16.255.22",
        "--rotation-marker",
        str(marker),
    )

    _run(*common_args)
    first_ca = _fingerprint(ca_cert)
    first_leaf = _fingerprint(server_cert)
    assert marker.exists()
    subprocess.run(
        ["openssl", "verify", "-CAfile", ca_cert, "-purpose", "sslserver", server_cert],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["openssl", "x509", "-in", server_cert, "-noout", "-checkhost", "gs-02.intern"],
        check=True,
        capture_output=True,
        text=True,
    )

    _run(*common_args, "--force-renew")
    assert _fingerprint(ca_cert) == first_ca
    assert _fingerprint(server_cert) != first_leaf

    foreign_cert = tmp_path / "foreign-ca.crt"
    foreign_key = tmp_path / "foreign-ca.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "ec",
            "-pkeyopt",
            "ec_paramgen_curve:prime256v1",
            "-nodes",
            "-days",
            "30",
            "-subj",
            "/CN=Foreign CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-keyout",
            foreign_key,
            "-out",
            foreign_cert,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    untrusted = subprocess.run(
        ["openssl", "verify", "-CAfile", foreign_cert, server_cert],
        capture_output=True,
        text=True,
    )
    assert untrusted.returncode != 0

    current_leaf = _fingerprint(server_cert)
    shutil.copy2(foreign_cert, ca_cert)
    refused = _run(*common_args, "--force-renew", check=False)
    assert refused.returncode != 0
    assert "CA certificate and private key do not match" in refused.stderr
    assert _fingerprint(server_cert) == current_leaf

    assert stat.S_IMODE(ca_key.stat().st_mode) == 0o600
    assert stat.S_IMODE(server_key.stat().st_mode) == 0o640
    assert stat.S_IMODE(server_cert.stat().st_mode) == 0o644


def test_vault_tls_uses_central_yaml_and_a_testable_maintenance_script() -> None:
    host_vars = (REPO_ROOT / "ansible/inventory/host_vars/gs-02.yml").read_text()
    module = (REPO_ROOT / "modules/nixos/luxnix/vault/default.nix").read_text()

    assert "vault.server.managedTls.enable" in host_vars
    assert "/var/lib/luxnix-vault-pki/ca.crt" in host_vars
    assert "lx-annotate-selfsigned.crt" not in host_vars
    assert "scripts/vault/maintain-server-tls.sh" in module
