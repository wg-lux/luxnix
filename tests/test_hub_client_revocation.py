"""Real certificate/CRL validation and disposable Nginx receiver acceptance."""

import datetime as dt
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "hub_crl", ROOT / "scripts/vault/publish-hub-crl.py"
)
crl_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crl_tool)
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def identity(name, issuer=None, ca=False):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    issuer_cert, issuer_key = issuer if issuer else (None, key)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_cert.subject if issuer_cert else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW - dt.timedelta(days=1))
        .not_valid_after(NOW + dt.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), False)
    )
    if not ca:
        builder = builder.add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH]
            ),
            False,
        )
    return builder.sign(issuer_key, hashes.SHA256()), key


def pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def crl(issuer, revoked=(), number=1, age=10, remaining=3600):
    cert, key = issuer
    builder = (
        x509.CertificateRevocationListBuilder()
        .issuer_name(cert.subject)
        .last_update(NOW - dt.timedelta(seconds=age))
        .next_update(NOW + dt.timedelta(seconds=remaining))
        .add_extension(x509.CRLNumber(number), critical=False)
    )
    for victim in revoked:
        builder = builder.add_revoked_certificate(
            x509.RevokedCertificateBuilder()
            .serial_number(victim.serial_number)
            .revocation_date(NOW - dt.timedelta(seconds=5))
            .build()
        )
    return pem(builder.sign(key, hashes.SHA256()))


@pytest.fixture
def chain(tmp_path):
    root = identity("root", ca=True)
    intermediate = identity("intermediate", root, ca=True)
    ca = tmp_path / "ca.pem"
    ca.write_bytes(pem(root[0]) + pem(intermediate[0]))
    return root, intermediate, ca


def test_complete_signed_chain_required(chain):
    root, intermediate, ca = chain
    crl_tool.validate(crl(root) + crl(intermediate), ca, 7200, 120, NOW)
    with pytest.raises(ValueError, match="each pinned CA"):
        crl_tool.validate(crl(intermediate), ca, 7200, 120, NOW)
    impostor = identity("intermediate", root, ca=True)
    with pytest.raises(ValueError, match="each pinned CA"):
        crl_tool.validate(crl(root) + crl(impostor), ca, 7200, 120, NOW)


@pytest.mark.parametrize(
    "age,remaining", [(8000, 3600), (-60, 3600), (30, -1), (10, 30)]
)
def test_stale_future_expired_and_nearly_expired_crls_rejected(chain, age, remaining):
    root, intermediate, ca = chain
    with pytest.raises(ValueError, match="stale|future|expired|expiry"):
        crl_tool.validate(
            crl(root) + crl(intermediate, age=age, remaining=remaining),
            ca,
            7200,
            120,
            NOW,
        )


def test_rejected_publication_preserves_bundle_and_rejects_rollback(chain, tmp_path):
    root, intermediate, ca = chain
    output = tmp_path / "published/crl.pem"
    valid = crl(root, number=2) + crl(intermediate, number=2)
    crl_tool.publish(valid, ca, output, 7200, 120)
    for bad in [b"not a CRL", crl(root), crl(root) + crl(intermediate)]:
        with pytest.raises(ValueError):
            crl_tool.publish(bad, ca, output, 7200, 120)
        assert output.read_bytes() == valid
    assert output.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize(
    "url", ["http://localhost/crl", "https://user:pass@localhost/crl"]
)
def test_unauthenticated_endpoints_refused(url):
    with pytest.raises(ValueError, match="HTTPS"):
        crl_tool.fetch(url, "/does/not/exist")


def write_identity(path, credentials, chain=b""):
    cert, key = credentials
    path.with_suffix(".crt").write_bytes(pem(cert) + chain)
    path.with_suffix(".key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def request(port, ca, client_path=None):
    context = ssl.create_default_context(cafile=str(ca))
    if client_path:
        context.load_cert_chain(
            str(client_path.with_suffix(".crt")), str(client_path.with_suffix(".key"))
        )
    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        with context.wrap_socket(sock, server_hostname="localhost") as conn:
            conn.sendall(
                b"GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            return conn.recv(4096)


def test_nginx_rejects_revoked_identity_after_reload(chain, tmp_path):
    nginx = shutil.which("nginx") or next(
        (str(p) for p in Path("/nix/store").glob("*-nginx-*/bin/nginx")), None
    )
    if not nginx:
        pytest.skip("Nginx binary required for real receiver acceptance")
    root, intermediate, ca = chain
    server = identity("localhost", root)
    old = identity("old-client", intermediate)
    new = identity("replacement-client", intermediate)
    for name, credentials in [("server", server), ("old", old), ("new", new)]:
        write_identity(tmp_path / name, credentials, pem(intermediate[0]))
    output = tmp_path / "crl.pem"
    crl_tool.publish(crl(root) + crl(intermediate), ca, output, 7200, 120)
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    ready = tmp_path / "ready"
    ready.touch()
    conf = tmp_path / "nginx.conf"
    conf.write_text(f"""
        daemon off;
        pid {tmp_path}/nginx.pid;
        error_log {tmp_path}/error.log;
        events {{}}
        http {{
          access_log off;
          server {{
            listen 127.0.0.1:{port} ssl;
            ssl_certificate {tmp_path}/server.crt;
            ssl_certificate_key {tmp_path}/server.key;
            ssl_client_certificate {ca};
            ssl_verify_depth 2;
            ssl_verify_client optional;
            ssl_crl {output};
            ssl_session_cache off;
            ssl_session_tickets off;
            location / {{
              if (!-f {ready}) {{ return 503; }}
              keepalive_requests 1;
              if ($ssl_client_verify != SUCCESS) {{ return 403; }}
              return 200 'accepted';
            }}
          }}
        }}
    """)
    process = subprocess.Popen(
        [nginx, "-p", str(tmp_path), "-c", str(conf)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env={
            k: v
            for k, v in os.environ.items()
            if k not in {"LD_LIBRARY_PATH", "LD_PRELOAD"}
        },
    )
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail(process.stderr.read().decode())
            try:
                assert b"200 OK" in request(port, ca, tmp_path / "old")
                break
            except ConnectionRefusedError:
                time.sleep(0.02)
        else:
            pytest.fail("Disposable Nginx did not start")
        assert b"200 OK" in request(port, ca, tmp_path / "new")
        crl_tool.publish(
            crl(root) + crl(intermediate, [old[0]], number=2), ca, output, 7200, 120
        )
        process.send_signal(__import__("signal").SIGHUP)
        for _ in range(100):
            response = request(port, ca, tmp_path / "old")
            if b"200 OK" not in response:
                break
            time.sleep(0.02)
        assert b"400 Bad Request" in response or b"403 Forbidden" in response
        assert b"200 OK" in request(port, ca, tmp_path / "new")
        ready.unlink()
        assert b"503 Service Temporarily Unavailable" in request(
            port, ca, tmp_path / "new"
        )
        # The same real TLS server proves publisher server authentication:
        # no trusted CA fallback on an unknown TLS issuer.
        wrong_ca = tmp_path / "wrong-ca.pem"
        wrong_ca.write_bytes(pem(identity("untrusted", ca=True)[0]))
        with pytest.raises(Exception, match="CERTIFICATE_VERIFY_FAILED"):
            crl_tool.fetch(f"https://localhost:{port}/", wrong_ca)
    finally:
        process.terminate()
        process.communicate(timeout=5)


def test_module_enforces_crl_and_startup_guard():
    source = (ROOT / "modules/nixos/services/lx-annotate-local/config.nix").read_text()
    assert "ssl_crl ${cfg.hub.transferApi.clientCrlFile};" in source
    assert 'requires = [ "luxnix-hub-crl-bootstrap.service" ];' in source
    assert "if (!-f /run/luxnix-hub-crl/ready)" in source
    assert 'OnUnitInactiveSec = "60s";' in source
