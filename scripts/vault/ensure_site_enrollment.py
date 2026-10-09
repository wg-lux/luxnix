#!/usr/bin/env python3
"""Hub-local reconciliation. Secret input is JSON on stdin; output is status only."""

import fcntl
import hashlib
import json
import os
from pathlib import Path
import ssl
import stat
import subprocess
import sys

from site_lifecycle import LifecycleError, Vault, identity, write_private

FILES = ("approle_role_id", "approle_secret_id", "source-node-secret")


def private_read(path, *, service_readable=False):
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & (0o037 if service_readable else 0o077)
    ):
        raise LifecycleError(
            "Unprotected or redirected enrollment file; operator recovery required."
        )
    value = path.read_text().strip()
    if not value:
        raise LifecycleError("Empty enrollment file; operator recovery required.")
    return value


def durable_write(path, value):
    write_private(path, value)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def ensure(vault, site, directory, installed, server_ca, kv_mount, recipient_path):
    """Caller holds the shared lifecycle lock. Never replace an existing identity."""
    role = identity(site)
    if any(
        name not in FILES or not isinstance(value, str) or not value.strip()
        for name, value in installed.items()
    ):
        raise LifecycleError("Invalid installed credential input.")
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise LifecycleError(
            "Enrollment directory must be private and owned by the caller."
        )
    base = "auth/approle/role/" + role
    role_id = vault.call("read", base + "/role-id")["data"]["role_id"]
    values = {}
    for name in FILES:
        saved = private_read(directory / name)
        deployed = installed.get(name)
        if saved and deployed and saved != deployed:
            raise LifecycleError(
                "Saved and installed credentials conflict; no identity was replaced."
            )
        values[name] = saved or deployed
    if values["approle_role_id"] and values["approle_role_id"] != role_id:
        raise LifecycleError("Role ID mismatch; no identity was replaced.")
    # Read canonical node secret BEFORE issuing credentials. A missing node with
    # installed state is data loss, not a reason to silently change its identity.
    node_path = kv_mount + "/data/nodes/" + site
    node = vault.call("read", node_path, empty=True)["data"]
    shared = node.get("data", {}).get("shared_secret")
    if shared is None:
        if any(values.values()):
            raise LifecycleError(
                "Vault node secret is missing for an existing enrollment."
            )
        # The existing enrolment command owns first creation (including CAS).
        raise LifecycleError(
            "Initial bundle must be created with the existing enrollment command."
        )
    if not shared or (
        values["source-node-secret"] and values["source-node-secret"] != shared
    ):
        raise LifecycleError("Node secret mismatch; no identity was replaced.")
    secret_id = values["approle_secret_id"]
    if not secret_id:
        raise LifecycleError(
            "Incomplete AppRole credentials; recover the saved bundle before retrying."
        )
    vault.call("write", base + "/secret-id/lookup", {"secret_id": secret_id})
    values.update(approle_role_id=role_id, **{"source-node-secret": shared})
    values["vault-server-ca.pem"] = server_ca.strip()
    public = vault.call("read", kv_mount + "/data/" + recipient_path)["data"]["data"][
        "public_key"
    ]
    result = subprocess.run(
        ["openssl", "pkey", "-pubin", "-text_pub", "-noout"],
        input=public,
        text=True,
        capture_output=True,
    )
    if result.returncode or "X25519" not in result.stdout:
        raise LifecycleError("Vault recipient public key is not X25519.")
    values["hub-recipient-current.pub.pem"] = public.strip()
    changed = False
    for name, value in values.items():
        saved = private_read(directory / name)
        if saved is None:
            durable_write(directory / name, value)
            changed = True
        elif saved != value:
            raise LifecycleError(
                "Saved trust material conflicts; explicit recovery is required."
            )
    return {
        "changed": changed,
        "ca_sha256": hashlib.sha256(ssl.PEM_cert_to_DER_cert(server_ca)).hexdigest(),
    }


def checked(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise LifecycleError(
            "Hub enrollment command failed; consult restricted hub/Vault logs."
        )


def reconcile(payload, state, root, receiver_directory, server_ca):
    site = payload["site"]
    if not site.endswith(".intern"):
        raise LifecycleError("Fleet sites must use the configured .intern domain.")
    role = identity(site)
    for path in (state, root):
        path.mkdir(mode=0o700, exist_ok=True)
        info = path.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise LifecycleError(
                "Hub state directories must be root-owned, private and not redirected."
            )
    # Separate fleet lock serializes concurrent fleet invocations, including the
    # existing commands which acquire the lifecycle lock themselves.
    with open(state / "fleet.lock", "a") as fleet_lock:
        fcntl.flock(fleet_lock, fcntl.LOCK_EX)
        if (state / role).exists():
            raise LifecycleError(
                "Site is contained; fleet enrollment cannot restore it."
            )
        checked(["luxnix-vault-reconcile-hub-sites", site])
        directory = root / site.removesuffix(".intern")
        installed = payload.get("installed", {})
        receiver = private_read(
            receiver_directory / (site.removesuffix(".intern") + "-source-node-secret"),
            service_readable=True,
        )
        if receiver:
            if installed.get("source-node-secret", receiver) != receiver:
                raise LifecycleError("Site and receiver node identities conflict.")
            installed["source-node-secret"] = receiver
        # A present directory, even an incomplete one, is never overwritten by
        # the credential-issuing command on retry.
        new_bundle = not directory.exists() and not directory.is_symlink()
        if new_bundle and not any(installed.get(name) for name in FILES[:2]):
            if installed.get("source-node-secret"):
                canonical = Vault().call(
                    "read", payload["kv_mount"] + "/data/nodes/" + site
                )
                if (
                    canonical["data"]["data"]["shared_secret"]
                    != installed["source-node-secret"]
                ):
                    raise LifecycleError("Existing node identity conflicts with Vault.")
            checked(["luxnix-vault-enroll-hub-site", site, str(directory)])
        with open(state / "lock", "a") as lifecycle_lock:
            fcntl.flock(lifecycle_lock, fcntl.LOCK_EX)
            if (state / role).exists():
                raise LifecycleError(
                    "Site containment changed during enrollment; stopped."
                )
            result = ensure(
                Vault(),
                site,
                directory,
                installed,
                server_ca,
                payload["kv_mount"],
                payload["recipient_path"],
            )
    return result


def main():
    payload = json.load(sys.stdin)
    token = payload.pop("token")
    if not token or any(c.isspace() for c in token) or os.geteuid() != 0:
        raise LifecycleError("Root and a nonempty Vault token are required.")
    os.umask(0o077)
    os.environ["VAULT_TOKEN"] = token
    try:
        result = reconcile(
            payload,
            Path("/var/lib/luxnix-vault-site-lifecycle"),
            Path("/root/vault-enrollment"),
            Path("/etc/secrets/vault/hub-pki"),
            Path(os.environ["VAULT_CACERT"]).read_text(),
        )
    finally:
        os.environ.pop("VAULT_TOKEN", None)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (LifecycleError, OSError, ValueError, KeyError):
        # Never include payloads, API responses or subprocess output in logs.
        print(
            "Enrollment reconciliation failed; no automatic credential rotation. "
            "Check protected bundle, containment state and Vault audit logs.",
            file=sys.stderr,
        )
        sys.exit(1)
