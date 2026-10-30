"""Converge explicitly selected KV-v2 secrets from Vault into OpenBao.

No discovery/export of unrelated secrets, initialization, deletion, token copying
or endpoint switching. API bodies and credentials never enter diagnostics.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import re
import resource
import ssl
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit

from lx_administration.secret_storage import encrypted_storage, _require_protected_swap
from lx_administration.yaml import load_unique_yaml_file


class MigrationError(RuntimeError):
    """Safe diagnostic without server-provided bodies."""


class Unavailable(MigrationError):
    pass


class ApiError(MigrationError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Secret API returned HTTP {status}")


def private_file(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve() != path:
        raise MigrationError("Credential requires an absolute path without symlinks")
    encrypted_storage(path, allow_runtime=True)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in (0, os.geteuid())
            or info.st_mode & 0o077
        ):
            raise MigrationError("Credential must be an owner-private regular file")
        data = stream.read(16385)
    if not data or len(data) > 16384:
        raise MigrationError("Credential is empty or oversized")
    return data


class Client:
    def __init__(self, config):
        if any(ord(char) <= 32 or ord(char) == 127 for char in config["url"]):
            raise MigrationError("Secret API URL contains control characters")
        self.url = urlsplit(config["url"])
        if (
            self.url.scheme != "https"
            or not self.url.hostname
            or self.url.username
            or self.url.password
            or self.url.query
            or self.url.fragment
            or self.url.path not in ("", "/")
        ):
            raise MigrationError("Secret API requires a pinned HTTPS origin")
        self.context = ssl.create_default_context(cafile=config["ca_file"])
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        if "client_key_file" in config or "client_cert_file" in config:
            private_file(config["client_key_file"])
            self.context.load_cert_chain(
                config["client_cert_file"], config["client_key_file"]
            )
        self.token_file = config["token_file"]
        self.token = None

    def call(self, method, path, data=None, *, authenticated=True):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            if self.token is None:
                try:
                    self.token = private_file(self.token_file).decode("ascii").strip()
                except UnicodeError:
                    raise MigrationError("Invalid API credential") from None
                if not re.fullmatch(r"[A-Za-z0-9._-]+", self.token):
                    raise MigrationError("Invalid API credential")
            headers["X-Vault-Token"] = self.token
        # http.client does not inherit proxy configuration or follow redirects.
        connection = http.client.HTTPSConnection(
            self.url.hostname, self.url.port or 443, context=self.context, timeout=10
        )
        try:
            connection.request(
                method,
                "/v1/" + path,
                body=None if data is None else json.dumps(data),
                headers=headers,
            )
            response = connection.getresponse()
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise MigrationError("Secret API response exceeds size limit")
            if response.status not in (200, 204):
                raise ApiError(response.status)
            try:
                result = json.loads(raw) if raw else {}
            except ValueError:
                raise MigrationError("Secret API returned invalid JSON") from None
            if not isinstance(result, dict):
                raise MigrationError("Secret API returned an invalid response")
            return result
        except ssl.SSLError:
            raise MigrationError("Secret API TLS verification failed") from None
        except (OSError, http.client.HTTPException):
            raise Unavailable("Secret API is unreachable") from None
        finally:
            connection.close()

    def read(self, path):
        for attempt in range(3):
            try:
                return self.call("GET", path)
            except Unavailable:
                if attempt == 2:
                    raise
                time.sleep(0.25 * 2**attempt)

    def active(self):
        try:
            health = self.call("GET", "sys/health", authenticated=False)
        except ApiError as error:
            if error.status in (429, 472, 473, 474, 501, 503, 530):
                return False
            raise
        if any(
            type(health.get(field)) is not bool for field in ("initialized", "sealed")
        ):
            raise MigrationError("Secret API returned malformed health status")
        return health["initialized"] and not health["sealed"]


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise MigrationError("Invalid migration identifier")
    return value


def kv_path(value):
    if (
        not isinstance(value, str)
        or not value
        or any(
            not re.fullmatch(r"[A-Za-z0-9_.@-]+", part) or part in (".", "..")
            for part in value.split("/")
        )
    ):
        raise MigrationError("Invalid KV path")
    return value


def validate(config):
    if (
        not isinstance(config, dict)
        or type(config.get("version")) is not int
        or config["version"] != 1
    ):
        raise MigrationError("Migration manifest requires version 1")
    if set(config) - {"version", "source", "target", "records"}:
        raise MigrationError("Unknown migration manifest field")
    for name in ("source", "target"):
        endpoint = config.get(name)
        if name == "source" and endpoint is None:
            continue
        if (
            not isinstance(endpoint, dict)
            or not {"url", "ca_file", "token_file"} <= endpoint.keys()
        ):
            raise MigrationError("Endpoint requires URL, CA and token-file references")
        if endpoint.keys() - {
            "url",
            "ca_file",
            "token_file",
            "client_key_file",
            "client_cert_file",
        }:
            raise MigrationError("Unknown endpoint option")
        if any(not isinstance(value, str) or not value for value in endpoint.values()):
            raise MigrationError("Endpoint values must be nonempty strings")
        if ("client_key_file" in endpoint) != ("client_cert_file" in endpoint):
            raise MigrationError("Mutual TLS requires both certificate and private key")
    if config.get("source") and config["source"]["url"].rstrip("/") == config["target"][
        "url"
    ].rstrip("/"):
        raise MigrationError("Source and target must be separate services")
    records = config.get("records")
    if not isinstance(records, list) or not records:
        raise MigrationError("Migration requires explicit nonempty records")
    names, destinations = set(), set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "id",
            "source_mount",
            "source_path",
            "target_mount",
            "target_path",
            "mode",
            "required_fields",
        }:
            raise MigrationError("Record has missing or unknown fields")
        name = identifier(record["id"])
        for field in ("source_mount", "target_mount", "source_path", "target_path"):
            kv_path(record[field])
        destination = (record["target_mount"], record["target_path"])
        if name in names or destination in destinations:
            raise MigrationError("Duplicate record or target path")
        names.add(name)
        destinations.add(destination)
        if record["mode"] not in ("immutable", "source_authoritative"):
            raise MigrationError(
                "Record mode must be immutable or source_authoritative"
            )
        fields = record["required_fields"]
        if (
            not isinstance(fields, list)
            or not fields
            or any(not isinstance(f, str) or not f for f in fields)
        ):
            raise MigrationError("Each record requires explicit required fields")
    return config


def snapshot(client, record, side):
    mount, path = record[f"{side}_mount"], record[f"{side}_path"]
    try:
        response = client.read(f"{mount}/data/{path}")
    except ApiError as error:
        if error.status != 404:
            raise
        # Distinguish an absent record from a deleted/destroyed version. Never
        # resurrect or overwrite a tombstone as if the destination were empty.
        try:
            client.read(f"{mount}/metadata/{path}")
        except ApiError as metadata_error:
            if metadata_error.status == 404:
                return None
            raise
        raise MigrationError("Selected KV record is deleted or unavailable")
    try:
        payload = response["data"]
        data, metadata = payload["data"], payload["metadata"]
        version = metadata["version"]
        if (
            not isinstance(data, dict)
            or not data
            or type(version) is not int
            or version < 1
            or metadata.get("destroyed")
            or metadata.get("deletion_time")
        ):
            raise ValueError
        if any(
            field not in data or data[field] in (None, "")
            for field in record["required_fields"]
        ):
            raise ValueError
        json.dumps(data, allow_nan=False)
        return version, data
    except (KeyError, TypeError, ValueError):
        raise MigrationError("Selected KV record is incomplete or malformed") from None


def same_data(left, right):
    # Canonical JSON distinguishes e.g. true from 1 and ignores object key order.
    return (
        left is not None
        and right is not None
        and json.dumps(left[1], sort_keys=True, separators=(",", ":"), allow_nan=False)
        == json.dumps(right[1], sort_keys=True, separators=(",", ":"), allow_nan=False)
    )


def reconcile(source, target, records, *, apply=False):
    if not target.active():
        raise MigrationError("OpenBao must be initialized, unsealed and active")
    source_active = False
    if source is not None:
        try:
            source_active = source.active()
        except Unavailable:
            pass
    mode = "vault_active" if source_active else "target_only"
    # Read and validate the entire wave before the first write. After a failure,
    # the next run re-reads state rather than trusting a local success marker.
    plan = []
    for record in records:
        destination = snapshot(target, record, "target")
        origin = snapshot(source, record, "source") if source_active else None
        if not source_active:
            if destination is None:
                raise MigrationError(
                    "Vault absent/inactive and a required OpenBao record is missing"
                )
            action = "verified_target"
        elif origin is None:
            raise MigrationError("An active Vault is missing a required source record")
        elif same_data(origin, destination):
            action = "unchanged"
        elif destination is None:
            action = "create"
        elif record["mode"] == "source_authoritative":
            action = "update"
        else:
            raise MigrationError("Immutable OpenBao record conflicts with Vault")
        plan.append((record, origin, destination, action))
    outcomes = []
    for record, origin, destination, action in plan:
        if apply and action in ("create", "update"):
            current = snapshot(source, record, "source")
            if not same_data(current, origin) or current[0] != origin[0]:
                raise MigrationError(
                    "Vault changed during provisioning; rerun the wave"
                )
            path = f"{record['target_mount']}/data/{record['target_path']}"
            try:
                target.call(
                    "POST",
                    path,
                    {
                        "options": {"cas": destination[0] if destination else 0},
                        "data": origin[1],
                    },
                )
            except (Unavailable, ApiError) as error:
                # A competing identical write or a lost acknowledgement can be
                # reconciled by readback. Never retry a blind write.
                if isinstance(error, ApiError) and error.status != 400:
                    raise
                if not same_data(snapshot(target, record, "target"), origin):
                    raise MigrationError(
                        "Concurrent or interrupted write differs; rerun after review"
                    ) from None
            if not same_data(snapshot(target, record, "target"), origin):
                raise MigrationError("OpenBao readback differs from Vault")
        outcomes.append(
            {
                "id": record["id"],
                "action": action,
                "source_version": origin[0] if origin else None,
            }
        )
    return {"mode": mode, "applied": apply, "records": outcomes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--record", action="append", help="Select record IDs; repeat for a scoped wave"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reviewed wave; default previews only",
    )
    args = parser.parse_args(argv)
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        _require_protected_swap()
        config = validate(load_unique_yaml_file(args.config))
        records = config["records"]
        if args.record:
            selected = set(args.record)
            if selected - {r["id"] for r in records}:
                raise MigrationError("Unknown selected record")
            records = [r for r in records if r["id"] in selected]
        source = Client(config["source"]) if config.get("source") else None
        result = reconcile(source, Client(config["target"]), records, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
        return 0
    except MigrationError as error:
        print(f"OpenBao provisioning failed: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError):
        # Config, credentials and server responses are deliberately excluded.
        print(
            "OpenBao provisioning failed; invalid configuration or credential file",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
