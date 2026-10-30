"""TPM-bound release client against software TPMs and a synthetic mTLS release server.

swtpm instances, the test CA and every secret are disposable and created per test.
A software TPM proves the client protocol and key handling, not the protection of
physical hosts (ENC-25); hardware evidence remains a separate acceptance step.
"""

import http.server
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "lx_administration/storage/tpm_release.py"
TOOLS = r"""
let
  f = builtins.getFlake ("git+file://" + builtins.toString ./.);
  host = f.nixosConfigurations.gc-10;
  pkgs = host.pkgs;
in pkgs.symlinkJoin {
  name = "tpm-release-test-tools";
  paths = [ host.config.luxnix.tpmReleaseClient.package pkgs.swtpm pkgs.tpm2-tools pkgs.openssl ];
}
"""


def load_module():
    spec = importlib.util.spec_from_file_location("tpm_release", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bin_dir():
    result = subprocess.run(
        ["nix", "build", "--no-link", "--print-out-paths", "--impure", "--expr", TOOLS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    return Path(result.stdout.strip().splitlines()[-1]) / "bin"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def free_port_pair():
    # The swtpm TCTI always uses the data port + 1 as its control port.
    for _ in range(50):
        port = free_port()
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port + 1))
            except OSError:
                continue
        return port
    raise RuntimeError("No adjacent free ports for swtpm")


class SoftwareTpm:
    def __init__(self, bin_dir, state):
        state.mkdir()
        self.bin_dir = bin_dir
        port = free_port_pair()
        self.process = subprocess.Popen(
            [
                bin_dir / "swtpm",
                "socket",
                "--tpm2",
                "--flags",
                "startup-clear",
                "--tpmstate",
                f"dir={state}",
                "--server",
                f"type=tcp,port={port}",
                "--ctrl",
                f"type=tcp,port={port + 1}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tcti = f"swtpm:host=127.0.0.1,port={port}"
        self.env = {**os.environ, "TPM2TOOLS_TCTI": tcti, "TPM2OPENSSL_TCTI": tcti}
        for _ in range(50):
            if (
                subprocess.run(
                    [bin_dir / "tpm2_getcap", "properties-fixed"], env=self.env, capture_output=True
                ).returncode
                == 0
            ):
                return
            threading.Event().wait(0.1)
        raise RuntimeError("swtpm did not start")

    def tool(self, *args, env=None):
        result = subprocess.run(
            [self.bin_dir / "luxnix-tpm-release", *map(str, args)],
            env={**self.env, **(env or {})},
            capture_output=True,
            check=False,
        )
        # No kernel resource manager here: drop transient objects between calls.
        subprocess.run(
            [self.bin_dir / "tpm2_flushcontext", "-t"], env=self.env, capture_output=True
        )
        return result

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=10)


@pytest.fixture
def tpms(bin_dir, tmp_path):
    started = [SoftwareTpm(bin_dir, tmp_path / name) for name in ("tpm-a", "tpm-b")]
    yield started
    for tpm in started:
        tpm.stop()


def openssl(bin_dir, *args, cwd):
    subprocess.run([bin_dir / "openssl", *args], cwd=cwd, check=True, capture_output=True)


def make_ca(bin_dir, directory):
    directory.mkdir(exist_ok=True)
    openssl(
        bin_dir,
        "req",
        "-x509",
        "-newkey",
        "ec",
        "-pkeyopt",
        "ec_paramgen_curve:P-256",
        "-nodes",
        "-subj",
        "/CN=test release CA",
        "-keyout",
        "ca.key",
        "-out",
        "ca.pem",
        "-days",
        "1",
        cwd=directory,
    )
    openssl(
        bin_dir,
        "req",
        "-x509",
        "-newkey",
        "ec",
        "-pkeyopt",
        "ec_paramgen_curve:P-256",
        "-nodes",
        "-subj",
        "/CN=localhost",
        "-addext",
        "subjectAltName=DNS:localhost",
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-keyout",
        "server.key",
        "-out",
        "server.pem",
        "-days",
        "1",
        cwd=directory,
    )
    return directory


def sign(bin_dir, ca, csr, out):
    openssl(
        bin_dir,
        "x509",
        "-req",
        "-in",
        str(csr),
        "-CA",
        "ca.pem",
        "-CAkey",
        "ca.key",
        "-CAcreateserial",
        "-days",
        "1",
        "-copy_extensions",
        "copy",
        "-out",
        str(out),
        cwd=ca,
    )


def enrolled(bin_dir, tpm, tmp_path, name="gc-10"):
    key, csr, cert = (
        tmp_path / "id/device.tss2.pem",
        tmp_path / "id/device.csr",
        tmp_path / "id/device.pem",
    )
    result = tpm.tool("identity-create", "--key", key, "--csr", csr, "--name", name, "--create-srk")
    assert result.returncode == 0, result.stderr
    ca = make_ca(bin_dir, tmp_path / "ca")
    sign(bin_dir, ca, csr, cert)
    return key, cert, ca


def test_identity_is_tpm_bound_sign_only_and_never_regenerated(bin_dir, tpms, tmp_path):
    tpm_a, tpm_b = tpms
    key, csr = tmp_path / "id/device.tss2.pem", tmp_path / "id/device.csr"

    missing = tpm_a.tool("identity-create", "--key", key, "--csr", csr, "--name", "gc-10")
    assert missing.returncode == 7 and b"srk-missing" in missing.stderr
    assert not key.exists()

    key, cert, ca = enrolled(bin_dir, tpm_a, tmp_path)
    assert key.stat().st_mode & 0o777 == 0o600
    info = load_module().decode_tss2(key.read_text())
    module = load_module()
    assert info["parent"] == module.SRK_HANDLE and info["empty_auth"]
    assert info["attributes"] & module.SIGN and not info["attributes"] & module.DECRYPT
    assert info["attributes"] & module.FIXED_TPM and info["attributes"] & module.FIXED_PARENT

    again = tpm_a.tool(
        "identity-create", "--key", key, "--csr", tmp_path / "other.csr", "--name", "gc-10"
    )
    assert again.returncode == 7 and b"identity-exists" in again.stderr

    assert (
        tpm_a.tool("identity-check", "--key", key, "--cert", cert, "--name", "gc-10").returncode
        == 0
    )
    wrong_name = tpm_a.tool("identity-check", "--key", key, "--cert", cert, "--name", "gc-09")
    assert wrong_name.returncode == 7 and b"identity-name" in wrong_name.stderr
    # A prefix of the enrolled name must not match (gc-1 against a gc-10 certificate).
    prefix = tpm_a.tool("identity-check", "--key", key, "--cert", cert, "--name", "gc-1")
    assert prefix.returncode == 7 and b"identity-name" in prefix.stderr
    injected = tpm_a.tool(
        "identity-create",
        "--key",
        tmp_path / "x/k",
        "--csr",
        tmp_path / "x/c",
        "--name",
        "gc-10/O=other",
    )
    assert injected.returncode == 2 and not (tmp_path / "x/k").exists()

    # A copy of the root disk on other hardware: same files, different TPM.
    assert (
        tpm_b.tool(
            "identity-create",
            "--key",
            tmp_path / "b/k",
            "--csr",
            tmp_path / "b/c",
            "--name",
            "other",
            "--create-srk",
        ).returncode
        == 0
    )
    foreign = tpm_b.tool("identity-check", "--key", key, "--cert", cert, "--name", "gc-10")
    assert foreign.returncode == 7 and b"identity-foreign-tpm" in foreign.stderr

    mismatch_cert = tmp_path / "b/c.pem"
    sign(bin_dir, ca, tmp_path / "b/c", mismatch_cert)
    mismatch = tpm_a.tool(
        "identity-check", "--key", key, "--cert", mismatch_cert, "--name", "other"
    )
    assert mismatch.returncode == 7 and b"identity-mismatch" in mismatch.stderr

    plaintext = tmp_path / "plain.key"
    openssl(
        bin_dir,
        "genpkey",
        "-algorithm",
        "EC",
        "-pkeyopt",
        "ec_paramgen_curve:P-256",
        "-out",
        str(plaintext),
        cwd=tmp_path,
    )
    rejected = tpm_a.tool("identity-check", "--key", plaintext, "--cert", cert, "--name", "gc-10")
    assert rejected.returncode == 7 and b"identity-not-tpm" in rejected.stderr


class ReleaseServer(http.server.ThreadingHTTPServer):
    """Mimics the OpenBao cert login and single-use KV v2 read of the VM test."""

    def __init__(self, ca):
        super().__init__(("127.0.0.1", 0), ReleaseHandler)
        context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=str(ca / "ca.pem"))
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(ca / "server.pem", ca / "server.key")
        self.socket = context.wrap_socket(self.socket, server_side=True)
        self.mode = "ok"
        self.secrets = {"gc-10/secrets": secrets.token_hex(32)}
        self.tokens = {}
        self.logins = 0
        self.reads = 0
        threading.Thread(target=self.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"https://localhost:{self.server_address[1]}"


class ReleaseHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body=None):
        payload = json.dumps(body or {}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def peer(self):
        subject = dict(item[0] for item in self.connection.getpeercert()["subject"])
        return subject["commonName"]

    def do_POST(self):
        server = self.server
        if server.mode == "sealed":
            return self.reply(503, {"errors": ["Vault is sealed"]})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path != "/v1/auth/cert/login" or body.get("name") != self.peer():
            return self.reply(400, {"errors": ["invalid certificate or role"]})
        if server.mode == "denied":
            return self.reply(403, {"errors": ["permission denied"]})
        if server.mode == "token-shape":
            return self.reply(200, {"auth": ["not", "an", "object"]})
        if server.mode == "token-newline":
            return self.reply(200, {"auth": {"client_token": "t\noutput = /tmp/injected"}})
        if server.mode == "top-level-list":
            payload = b"[]"
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            return self.wfile.write(payload)
        server.logins += 1
        token = secrets.token_hex(16)
        server.tokens[token] = {"host": self.peer(), "uses": 1}
        return self.reply(200, {"auth": {"client_token": token, "lease_duration": 30}})

    def do_GET(self):
        server = self.server
        grant = server.tokens.get(self.headers.get("X-Vault-Token", ""))
        prefix = "/v1/volume-release/data/"
        if not grant or grant["uses"] < 1 or not self.path.startswith(prefix):
            return self.reply(403, {"errors": ["permission denied"]})
        grant["uses"] -= 1
        record = self.path[len(prefix) :]
        if not record.startswith(grant["host"] + "/"):
            return self.reply(403, {"errors": ["permission denied"]})
        if record not in server.secrets:
            return self.reply(404, {})
        server.reads += 1
        if server.mode == "record-shape":
            return self.reply(200, {"data": "not an object"})
        return self.reply(200, {"data": {"data": {"key": server.secrets[record]}}})


def test_fetch_releases_one_volume_and_classifies_failures(bin_dir, tpms, tmp_path):
    tpm_a, _ = tpms
    key, cert, ca = enrolled(bin_dir, tpm_a, tmp_path)
    server = ReleaseServer(ca)
    try:

        def fetch(volume="secrets", url=None, pinned=ca / "ca.pem", env=None):
            return tpm_a.tool(
                "fetch",
                "--url",
                url or server.url,
                "--ca",
                pinned,
                "--cert",
                cert,
                "--key",
                key,
                "--name",
                "gc-10",
                "--volume",
                volume,
                env=env,
            )

        released = fetch()
        secret = server.secrets["gc-10/secrets"].encode()
        assert released.returncode == 0, released.stderr
        assert released.stdout == secret
        assert secret not in released.stderr
        assert (server.logins, server.reads) == (1, 1)
        assert all(grant["uses"] == 0 for grant in server.tokens.values())

        missing = fetch("app-storage")
        assert missing.returncode == 6 and b"release-not-found" in missing.stderr

        server.mode = "denied"
        denied = fetch()
        assert denied.returncode == 4 and b"release-denied" in denied.stderr and not denied.stdout

        server.mode = "sealed"
        sealed = fetch()
        assert sealed.returncode == 5 and b"release-sealed" in sealed.stderr and not sealed.stdout

        server.mode = "ok"
        other_ca = make_ca(bin_dir, tmp_path / "other-ca")
        unpinned = fetch(pinned=other_ca / "ca.pem")
        assert unpinned.returncode == 4 and b"release-tls-rejected" in unpinned.stderr

        unreachable = fetch(url=f"https://localhost:{free_port()}")
        assert unreachable.returncode == 3 and b"release-unreachable" in unreachable.stderr

        plain = fetch(url=server.url.replace("https://", "http://"))
        assert plain.returncode == 2 and b"release-config" in plain.stderr

        # mTLS with a plaintext key would work; the client must refuse before any request.
        logins = server.logins
        plaintext = tmp_path / "plain.key"
        openssl(
            bin_dir,
            "genpkey",
            "-algorithm",
            "EC",
            "-pkeyopt",
            "ec_paramgen_curve:P-256",
            "-out",
            str(plaintext),
            cwd=tmp_path,
        )
        unbound = tpm_a.tool(
            "fetch",
            "--url",
            server.url,
            "--ca",
            ca / "ca.pem",
            "--cert",
            cert,
            "--key",
            plaintext,
            "--name",
            "gc-10",
            "--volume",
            "secrets",
        )
        assert unbound.returncode == 7 and b"identity-not-tpm" in unbound.stderr
        assert server.logins == logins

        # Path segments cannot address another host's record or API path.
        for volume in ("../secrets", "a/b", "secrets?x=1", ""):
            traversal = fetch(volume)
            assert traversal.returncode == 2 and b"release-config" in traversal.stderr

        # Ambient curl configuration is ignored: a ~/.curlrc output directive must not apply.
        home = tmp_path / "home"
        home.mkdir()
        leak = tmp_path / "leaked-body"
        (home / ".curlrc").write_text(f'output = "{leak}"\n')
        ambient = fetch(env={"HOME": str(home), "CURL_HOME": str(home)})
        assert ambient.returncode == 0 and ambient.stdout == secret and not leak.exists()

        # Malformed server responses fail closed with a classified error, never a traceback.
        for mode, code, reason in (
            ("token-shape", 4, b"release-denied"),
            ("token-newline", 2, b"release-malformed"),
            ("top-level-list", 2, b"release-malformed"),
            ("record-shape", 6, b"release-not-found"),
        ):
            server.mode = mode
            result = fetch()
            assert result.returncode == code and reason in result.stderr, (mode, result.stderr)
            assert b"Traceback" not in result.stderr and not result.stdout
        assert not Path("/tmp/injected").exists()
    finally:
        server.shutdown()


def test_tokens_and_bodies_stay_out_of_process_arguments(tmp_path):
    module = load_module()
    token = "s." + secrets.token_hex(16)
    arguments = module.curl_arguments(tmp_path / "ca", tmp_path / "cert", tmp_path / "key")
    config = module._curl_config(
        "https://gs-02.intern:8300/v1/x", token=token, body={"name": "gc-10"}
    )
    assert token not in " ".join(arguments)
    assert arguments[-2:] == ["--config", "-"]
    assert arguments[:2] == ["curl", "--disable"]
    with pytest.raises(module.ReleaseError) as error:
        module._curl_config("https://gs-02.intern:8300/v1/x", token="t\r\nurl = https://evil")
    assert error.value.reason == "release-malformed"
    assert f'header = "X-Vault-Token: {token}"'.encode() in config
