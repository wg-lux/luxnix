#!/usr/bin/env python3
"""Explicit, hub-local site containment. Never operate on production at import time."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import ssl
import hashlib
import sys


class LifecycleError(RuntimeError):
    pass


class Vault:
    def call(self, verb, path, payload=None, *, empty=False):
        command = ["vault", verb, "-format=json", path]
        if payload is not None:
            command.append("-")
        result = subprocess.run(
            command,
            input=json.dumps(payload) if payload is not None else None,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode:
            # Vault CLI uses exit 2 both for empty LIST and server failures: only
            # its specific missing-value diagnostic is an empty list.
            if (
                empty
                and result.returncode == 2
                and result.stderr.startswith("No value found at ")
            ):
                return {"data": {"keys": []}}
            raise LifecycleError(
                f"Vault {verb} failed; containment remains in place. Consult "
                "restricted Vault audit logs."
            )
        output = result.stdout.strip()
        # Bodyless successful writes print a CLI success line even with -format.
        if verb == "write" and output.startswith("Success! Data written to:"):
            return {}
        return json.loads(output) if output else {}


def identity(site):
    if (
        len(site) > 253
        or site != site.lower()
        or "." not in site
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in site.split(".")
        )
    ):
        raise LifecycleError("An exact lowercase site FQDN is required.")
    return "site-" + site.translate(str.maketrans(".-", "__"))


def write_private(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(value + "\n")
        stream.flush()
        os.fsync(stream.fileno())


class Lifecycle:
    def __init__(self, vault, directory, kv_mount, pki_mount="pki", server_ca=None):
        self.vault = vault
        self.directory = Path(directory)
        self.kv_mount = kv_mount
        self.pki_mount = pki_mount
        self.server_ca = server_ca

    def state(self, site, phase):
        target = self.directory / identity(site)
        temporary = self.directory / (identity(site) + ".new")
        # Protected root-owned directory; atomic marker survives process failure.
        with open(temporary, "w") as stream:
            os.chmod(temporary, 0o600)
            json.dump({"site": site, "phase": phase}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def require(self, site, phase):
        marker = self.directory / identity(site)
        record = json.loads(marker.read_text()) if marker.exists() else {}
        if record.get("phase") != phase or record.get("site") != site:
            raise LifecycleError(
                f"Site must be in {phase} state; rerun containment after any "
                "partial failure."
            )

    def contain(self, site):
        role = identity(site)
        policy = "lx-hub-" + role
        domains = self.vault.call("read", self.pki_mount + "/roles/" + role)[
            "data"
        ].get("allowed_domains")
        if domains != [site]:
            raise LifecycleError("PKI role is not exclusive to this exact site.")
        self.state(site, "containing")
        self.vault.call(
            "write",
            "sys/policies/acl/" + policy,
            {"policy": 'path "*" { capabilities = ["deny"] }'},
        )
        base = "auth/approle/role/" + role
        ids = self.vault.call("list", base + "/secret-id", empty=True)["data"]["keys"]
        for accessor in ids:
            self.vault.call(
                "write",
                base + "/secret-id-accessor/destroy",
                {"secret_id_accessor": accessor},
            )
        tokens = self.vault.call("list", "auth/token/accessors", empty=True)["data"][
            "keys"
        ]
        for accessor in tokens:
            info = self.vault.call(
                "write", "auth/token/lookup-accessor", {"accessor": accessor}
            )["data"]
            if policy not in info.get("policies", []):
                continue
            if (info.get("meta") or {}).get("role_name") != role:
                raise LifecycleError(
                    "Site policy appears on a token of unexpected origin; "
                    "custodian review required."
                )
            self.vault.call(
                "write", "auth/token/revoke-accessor", {"accessor": accessor}
            )
        self.state(site, "contained")

    def rotate(self, site, output):
        role = identity(site)
        self.require(site, "contained")
        # Require a new protected directory, never overwrite a previous bundle.
        output = Path(output)
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.state(site, "rotating")
        server_ca = Path(self.server_ca).read_text()
        fingerprint = (
            hashlib.sha256(ssl.PEM_cert_to_DER_cert(server_ca)).hexdigest().upper()
        )
        client_ca = self.vault.call("read", self.pki_mount + "/cert/ca")["data"][
            "certificate"
        ]
        path = self.kv_mount + "/data/nodes/" + site
        current = self.vault.call("read", path)["data"]
        data = current["data"]
        if not data.get("shared_secret") or not isinstance(
            current["metadata"]["version"], int
        ):
            raise LifecycleError(
                "Existing node secret/version is invalid; refusing rotation."
            )
        data["shared_secret"] = secrets.token_urlsafe(48)
        self.vault.call(
            "write",
            path,
            {"options": {"cas": current["metadata"]["version"]}, "data": data},
        )
        observed = self.vault.call("read", path)["data"]
        if (
            observed["data"] != data
            or observed["metadata"]["version"] != current["metadata"]["version"] + 1
        ):
            raise LifecycleError(
                "Node secret changed concurrently; keep the site contained."
            )
        role_id = self.vault.call("read", "auth/approle/role/" + role + "/role-id")[
            "data"
        ]["role_id"]
        secret_id = self.vault.call(
            "write", "auth/approle/role/" + role + "/secret-id", {}
        )["data"]["secret_id"]
        write_private(output / "approle_role_id", role_id)
        write_private(output / "approle_secret_id", secret_id)
        write_private(output / "source-node-secret", data["shared_secret"])
        write_private(output / "vault-server-ca.pem", server_ca.rstrip())
        write_private(output / "vault-server-ca.sha256", fingerprint)
        write_private(output / "client-ca.pem", client_ca.rstrip())
        self.state(site, "rotated")

    def resume(self, site):
        identity(site)
        self.require(site, "rotated")
        # The policy remains deny until the operator explicitly reconciles it.
        (self.directory / identity(site)).unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["contain", "rotate", "resume"])
    parser.add_argument("site")
    parser.add_argument("--output-directory")
    parser.add_argument("--accept-consumer-verification", action="store_true")
    args = parser.parse_args()
    try:
        identity(args.site)
        if os.geteuid() != 0:
            raise LifecycleError("Run as root on the authoritative hub.")
        if not os.environ.get("VAULT_TOKEN") or not os.environ.get(
            "VAULT_ADDR", ""
        ).startswith("https://"):
            raise LifecycleError(
                "Authenticated HTTPS VAULT_ADDR and administrative VAULT_TOKEN "
                "are required."
            )
        if os.environ.get("VAULT_SKIP_VERIFY", "").lower() not in ("", "false", "0"):
            raise LifecycleError("TLS verification must remain enabled.")
        directory = Path("/var/lib/luxnix-vault-site-lifecycle")
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        with open(directory / "lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            lifecycle = Lifecycle(
                Vault(),
                directory,
                os.environ["LUXNIX_VAULT_KV_MOUNT"],
                os.environ["LUXNIX_VAULT_PKI_MOUNT"],
                os.environ["LUXNIX_VAULT_SERVER_CA"],
            )
            if args.action == "contain":
                lifecycle.contain(args.site)
            elif args.action == "rotate":
                if not args.output_directory:
                    raise LifecycleError(
                        "rotate requires --output-directory pointing to a new "
                        "directory."
                    )
                lifecycle.rotate(args.site, args.output_directory)
            else:
                if not args.accept_consumer_verification:
                    raise LifecycleError(
                        "resume requires --accept-consumer-verification after "
                        "both node records and old-credential rejection were checked."
                    )
                lifecycle.resume(args.site)
        print(
            json.dumps(
                {
                    "event": "vault.site_lifecycle",
                    "action": args.action,
                    "site": args.site,
                    "result": "complete",
                }
            )
        )
        if args.action == "resume":
            print(
                "Containment marker removed; explicitly reconcile this site to "
                "restore policy."
            )
        return 0
    except (LifecycleError, OSError, ValueError, KeyError):
        # No exception payload: API/parser errors may contain sensitive material.
        print(
            "ERROR: site lifecycle failed; retain containment and inspect "
            "restricted audit evidence. "
            "After a partial rotation, contain again before generating another "
            "fresh bundle.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
