"""Guest-only integration assertions. File certificates do NOT satisfy ENC-06.

All private keys, Shamir shares, tokens and volume secrets are generated in the
disposable VM. Never return API payloads or secret values to the test driver.
"""

import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request


STATE = Path("/run/bao-test")
URL = "https://127.0.0.1:8300/v1/"


class KVUpgradePending(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def command(*args):
    subprocess.run(args, cwd=STATE, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def prepare():
    STATE.mkdir(mode=0o700)
    (STATE / "disk.key").write_bytes(secrets.token_bytes(32))
    command("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", "ca.key", "-out", "ca.pem", "-days", "1", "-subj", "/CN=VM CA",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    for name in ("server", "a", "b"):
        command("openssl", "req", "-newkey", "rsa:2048", "-nodes",
                "-keyout", f"{name}.key", "-out", f"{name}.csr", "-subj", f"/CN={name}")
        (STATE / "extensions").write_text(
            "basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
            + ("extendedKeyUsage=serverAuth\nsubjectAltName=IP:127.0.0.1\n"
               if name == "server" else "extendedKeyUsage=clientAuth\n")
        )
        command("openssl", "x509", "-req", "-in", f"{name}.csr", "-CA", "ca.pem",
                "-CAkey", "ca.key", "-CAcreateserial", "-days", "1",
                "-extfile", "extensions", "-out", f"{name}.pem")


def request(method, path, *, token=None, client=None, data=None, expected=200, timeout=10):
    context = ssl.create_default_context(cafile=str(STATE / "ca.pem"))
    if client:
        context.load_cert_chain(STATE / f"{client}.pem", STATE / f"{client}.key")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    req = urllib.request.Request(URL + path, method=method, headers=headers,
                                 data=None if data is None else json.dumps(data).encode())
    try:
        with urllib.request.urlopen(req, context=context, timeout=timeout) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    result = json.loads(body) if body else {}
    if status == 400 and any("Upgrading from non-versioned" in error
                             for error in result.get("errors", [])):
        raise KVUpgradePending("KV v2 initialization is not complete")
    require(status == expected, f"{method} {path}: expected HTTP {expected}, got {status}")
    return result


def exercise():
    require(request("GET", "sys/seal-status")["sealed"], "Must start sealed")
    # Initial Raft election can exceed the ordinary 10-second API deadline.
    # This bounds setup only; release requests retain the shorter deadline.
    init = request("POST", "sys/init", data={"secret_shares": 3, "secret_threshold": 2}, timeout=60)
    root = init["root_token"]
    # Shamir material stays in guest RAM; no CLI output, store paths or host logs.
    first = request("POST", "sys/unseal", data={"key": init["keys_base64"][0]})
    require(first["sealed"], "One share must not unseal")
    duplicate = request("POST", "sys/unseal", data={"key": init["keys_base64"][0]})
    require(duplicate["sealed"] and duplicate["progress"] == 1,
            "Repeating one custodian share must not count as a second custodian")
    reset = request("POST", "sys/unseal", data={"reset": True})
    require(reset["sealed"] and reset["progress"] == 0, "Reset must discard partial quorum")
    request("POST", "sys/unseal", data={"key": init["keys_base64"][0]})
    second = request("POST", "sys/unseal", data={"key": init["keys_base64"][1]})
    require(not second["sealed"], "Two shares must unseal")
    for attempt in range(60):
        health = request("GET", "sys/seal-status")
        if not health["sealed"]:
            try:
                request("GET", "sys/health")
                break
            except RuntimeError:
                pass
        time.sleep(1)
    else:
        raise RuntimeError("Raft leader did not become ready")

    def admin(method, path, data=None, expected=204):
        return request(method, path, token=root, data=data, expected=expected)

    audit = admin("GET", "sys/audit", expected=200)
    require("release/" in audit["data"], "Declarative audit device missing")
    def mount_kv(name):
        admin("POST", f"sys/mounts/{name}", {"type": "kv", "options": {"version": "2"}})
        # New KV v2 mounts initialize asynchronously. Only this specific setup
        # condition may be retried; authorization failures must never be retried.
        for attempt in range(30):
            try:
                admin("GET", f"{name}/config", expected=200)
                return
            except KVUpgradePending:
                time.sleep(1)
        raise RuntimeError("KV v2 initialization deadline exceeded")

    mount_kv("volume-release")
    admin("POST", "sys/auth/cert", {"type": "cert"})
    volumes = ("secrets", "app-storage")
    values = {}
    for host in ("a", "b"):
        policy = "\n".join(
            f'path "volume-release/data/{host}/{volume}" {{ capabilities = ["read"] }}'
            for volume in volumes
        )
        admin("PUT", f"sys/policies/acl/release-{host}", {"policy": policy})
        admin("POST", f"auth/cert/certs/{host}", {
            "certificate": (STATE / f"{host}.pem").read_text(),
            "display_name": host, "token_policies": [f"release-{host}"],
            "token_no_default_policy": True, "token_num_uses": 1,
            "token_ttl": "30s", "token_max_ttl": "30s",
            "token_explicit_max_ttl": "30s", "token_type": "service",
        })
        for volume in volumes:
            path = f"volume-release/data/{host}/{volume}"
            values[path] = secrets.token_hex(32)
            admin("POST", path, {"options": {"cas": 0}, "data": {"key": values[path]}}, expected=200)

    def login(host, expected=200):
        response = request("POST", "auth/cert/login", client=host,
                           data={"name": host}, expected=expected)
        if expected != 200:
            return None
        auth = response["auth"]
        require(0 < auth["lease_duration"] <= 30, "Release TTL exceeds 30 seconds")
        require(auth["entity_id"], "Certificate identity missing")
        return auth

    identities = {}
    for host in ("a", "b"):
        for volume in volumes:
            auth = login(host)
            identities[host] = auth["entity_id"]
            path = f"volume-release/data/{host}/{volume}"
            read = request("GET", path, token=auth["client_token"], client=host)
            require(read["data"]["data"]["key"] == values[path], "Wrong volume value")
            request("GET", path, token=auth["client_token"], client=host, expected=403)
        other = "b" if host == "a" else "a"
        request("GET", f"volume-release/data/{other}/secrets",
                token=login(host)["client_token"], client=host, expected=403)
        request("GET", f"volume-release/data/{host}/unassigned",
                token=login(host)["client_token"], client=host, expected=403)
    # A caller cannot select the other host's role with its own certificate.
    request("POST", "auth/cert/login", client="b", data={"name": "a"}, expected=400)

    path = "volume-release/data/a/secrets"
    auth = login("a")
    lookup = admin("POST", "auth/token/lookup", {"token": auth["client_token"]}, expected=200)
    require(lookup["data"]["num_uses"] == 1, "Release token is not single-use")
    admin("POST", "auth/token/revoke-accessor", {"accessor": auth["accessor"]})
    request("GET", path, token=auth["client_token"], client="a", expected=403)

    expired = login("b")
    time.sleep(32)
    request("GET", "volume-release/data/b/secrets", token=expired["client_token"],
            client="b", expected=403)

    # Role deletion ALONE does not revoke existing tokens. Demonstrate this
    # upstream boundary, then test the fail-closed removal workflow explicitly.
    stale, blocked = login("a"), login("a")
    admin("DELETE", "auth/cert/certs/a")
    login("a", expected=400)
    request("GET", path, token=stale["client_token"], client="a")
    admin("PUT", "sys/policies/acl/release-a", {
        "policy": 'path "volume-release/*" { capabilities = ["deny"] }'})
    request("GET", path, token=blocked["client_token"], client="a", expected=403)
    # Safe order for the second host: deny first (including outstanding tokens),
    # remove the auth role second. Retain the deny policy until all tokens expire.
    blocked = login("b")
    admin("PUT", "sys/policies/acl/release-b", {
        "policy": 'path "volume-release/*" { capabilities = ["deny"] }'})
    admin("DELETE", "auth/cert/certs/b")
    login("b", expected=400)
    request("GET", "volume-release/data/b/secrets", token=blocked["client_token"],
            client="b", expected=403)

    mount_kv("application")
    app_value = secrets.token_hex(32)
    admin("POST", "application/data/config", {"options": {"cas": 0}, "data": {"key": app_value}}, expected=200)
    admin("PUT", "sys/policies/acl/application", {
        "policy": 'path "application/data/*" { capabilities = ["read"] }'})
    app = admin("POST", "auth/token/create", {
        "policies": ["application"], "no_default_policy": True, "ttl": "5m"
    }, expected=200)["auth"]["client_token"]
    require(request("GET", "application/data/config", token=app)["data"]["data"]["key"]
            == app_value, "Application token must work on its own mount")
    request("GET", path, token=app, expected=403)
    audit_text = Path("/var/lib/openbao/audit.jsonl").read_text()
    require(all(value not in audit_text for value in values.values()), "Audit leaked volume secret")
    entries = [json.loads(line) for line in audit_text.splitlines()]
    require(any(e.get("type") == "response"
                and e.get("request", {}).get("path") == path
                and e.get("auth", {}).get("entity_id") == identities["a"]
                and e.get("response", {}).get("data", {}).get("data", {}).get("key", "").startswith("hmac-sha256:")
                for e in entries), "Audit lacks authenticated identity, release path or HMAC value")
    journal = subprocess.check_output(["journalctl", "-u", "openbao", "--no-pager"], text=True)
    require(all(value not in journal for value in values.values()), "Journal leaked volume secret")
    # Keep only a token in private tmpfs for the post-restart negative request.
    (STATE / "restart-token").write_text(app)


def sealed():
    state = request("GET", "sys/seal-status")
    require(state["initialized"] and state["sealed"], "Restart must retain state and reseal")
    response = request("GET", "volume-release/data/a/secrets",
                       token=(STATE / "restart-token").read_text(), client="a", expected=503)
    require(any("sealed" in error.lower() for error in response["errors"]),
            "Client must receive an explicit sealed error, without fallback")


if __name__ == "__main__":
    os.umask(0o077)
    {"prepare": prepare, "exercise": exercise, "sealed": sealed}[sys.argv[1]]()
