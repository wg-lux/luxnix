"""Real TLS API/CLI rehearsal; all keys and service state live in guest tmpfs."""

import json
import os
from pathlib import Path
import secrets
import subprocess
import time

import yaml

from lx_administration.storage.bao_migration import Client, ApiError, Unavailable

ROOT = Path("/run/bao-migration")
os.umask(0o077)
ROOT.mkdir()
subprocess.run(
    [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        str(ROOT / "tls.key"),
        "-out",
        str(ROOT / "ca.pem"),
        "-days",
        "1",
        "-subj",
        "/CN=localhost",
        "-addext",
        "subjectAltName=DNS:localhost",
    ],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)


def endpoint(name, port):
    return {
        "url": f"https://localhost:{port}",
        "ca_file": str(ROOT / "ca.pem"),
        "token_file": str(ROOT / f"{name}.token"),
    }


def launch(name, binary, port):
    directory = ROOT / name
    directory.mkdir(exist_ok=True)
    config = {
        "disable_mlock": True,
        "storage": {"file": {"path": str(directory)}},
        "listener": {
            "tcp": {
                "address": f"127.0.0.1:{port}",
                "tls_cert_file": str(ROOT / "ca.pem"),
                "tls_key_file": str(ROOT / "tls.key"),
            }
        },
        "api_addr": f"https://localhost:{port}",
    }
    path = ROOT / f"{name}.json"
    path.write_text(json.dumps(config))
    process = subprocess.Popen(
        [binary, "server", f"-config={path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = Client(endpoint(name, port))
    for _ in range(100):
        try:
            client.active()
            break
        except Unavailable:
            if process.poll() is not None:
                raise RuntimeError("Test daemon exited")
            time.sleep(0.1)
    else:
        raise RuntimeError("Test daemon failed to listen")
    init = client.call(
        "PUT",
        "sys/init",
        {
            "secret_shares": 1,
            "secret_threshold": 1,
        },
        authenticated=False,
    )
    Path(client.token_file).write_text(init["root_token"])
    client.call("PUT", "sys/unseal", {"key": init["keys"][0]}, authenticated=False)
    for _ in range(100):
        if client.active():
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Test daemon did not become active")
    client.call("POST", "sys/mounts/kv", {"type": "kv", "options": {"version": "2"}})
    return process, client


def write(client, value):
    for _ in range(100):
        try:
            client.call("POST", "kv/data/application", {"data": {"key": value}})
            return
        except ApiError as error:
            if error.status != 400:
                raise
            time.sleep(0.1)
    raise RuntimeError("KV engine did not become ready")


vault, source = launch("vault", "vault", 8200)
bao, target = launch("bao", "bao", 8300)
value = secrets.token_hex(32)
write(source, value)
protected_values = [
    value,
    Path(source.token_file).read_text(),
    Path(target.token_file).read_text(),
]
# Wait for the freshly enabled target KV-v2 engine without initializing a record.
for _ in range(100):
    try:
        target.call("GET", "kv/config")
        break
    except ApiError as error:
        if error.status != 400:
            raise
        time.sleep(0.1)
else:
    raise RuntimeError("Target KV engine did not become ready")

manifest = {
    "version": 1,
    "source": endpoint("vault", 8200),
    "target": endpoint("bao", 8300),
    "records": [
        {
            "id": "application",
            "source_mount": "kv",
            "source_path": "application",
            "target_mount": "kv",
            "target_path": "application",
            "mode": "immutable",
            "required_fields": ["key"],
        }
    ],
}


def run(*, apply=True, success=True):
    config = ROOT / "migration.yml"
    config.write_text(yaml.safe_dump(manifest))
    args = [
        "python",
        "-m",
        "lx_administration.storage.bao_migration",
        "--config",
        str(config),
    ]
    if apply:
        args.append("--apply")
    result = subprocess.run(args, capture_output=True, text=True)
    assert (result.returncode == 0) is success, "Unexpected provisioning exit status"
    assert all(
        secret not in result.stdout + result.stderr for secret in protected_values
    ), "Secret leaked to diagnostics"
    return json.loads(result.stdout) if success else None


assert run(apply=False)["records"][0]["action"] == "create"
assert run()["records"][0]["action"] == "create"
assert run()["records"][0]["action"] == "unchanged"
assert target.read("kv/data/application")["data"]["metadata"]["version"] == 1
assert target.read("kv/data/application")["data"]["data"] == {"key": value}

# Existing but unauthenticated source is not mistaken for a retired server.
token = Path(source.token_file).read_text()
Path(source.token_file).write_text("invalid-test-credential")
run(success=False)
Path(source.token_file).write_text(token)

manifest["source"]["url"] = "https://127.0.0.1:8200"
run(success=False)  # a trusted CA with the wrong hostname is still rejected
manifest["source"]["url"] = "https://localhost:8200"
replacement = secrets.token_hex(32)
protected_values.append(replacement)
write(source, replacement)
run(success=False)  # immutable conflict
manifest["records"][0]["mode"] = "source_authoritative"
assert run()["records"][0]["action"] == "update"
assert run()["records"][0]["action"] == "unchanged"
assert target.read("kv/data/application")["data"]["metadata"]["version"] == 2
assert (
    target.read("kv/data/application")["data"]["data"]
    == source.read("kv/data/application")["data"]["data"]
)

vault.terminate()
vault.wait(timeout=10)
Path(source.token_file).unlink()  # no source credential required after retirement
assert run()["mode"] == "target_only"
manifest["source"] = None
assert run()["records"][0]["action"] == "verified_target"
manifest["records"][0]["target_path"] = "missing"
run(success=False)
manifest["records"][0]["target_path"] = "application"
target.call("DELETE", "kv/data/application")
run(success=False)  # deleted values are never resurrected
bao.terminate()
bao.wait(timeout=10)
print("Real Vault/OpenBao TLS migration and retirement rehearsal passed")
