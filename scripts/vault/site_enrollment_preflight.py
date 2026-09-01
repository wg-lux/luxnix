#!/usr/bin/env python3
"""Validate the non-secret prerequisites for one Vault site enrollment."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, cast

from lx_administration.yaml import load_unique_yaml_file


HOST_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
REQUIRED_GROUPS = frozenset({"active_clients", "gpu_client", "endoreg_client"})
RunCommand = Callable[[list[str], Path], str]


@dataclass(frozen=True)
class CheckResult:
    id: str
    status: str
    detail: str


def run_command(command: list[str], cwd: Path) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError(f"required command is unavailable: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"{command[0]} exited with status {error.returncode}"
        ) from error
    return completed.stdout.strip()


def yaml_mapping(path: Path) -> dict[str, Any]:
    value = load_unique_yaml_file(path)
    if not isinstance(value, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    return cast(dict[str, Any], value)


def parse_inventory(path: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    host_addresses: dict[str, str] = {}
    groups: dict[str, set[str]] = {}
    current_group = "all"

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1]
            groups.setdefault(current_group, set())
            continue
        if current_group.endswith(":vars") or current_group.endswith(":children"):
            continue

        fields = shlex.split(line, comments=True)
        if not fields or "=" in fields[0]:
            continue
        host = fields[0]
        groups.setdefault(current_group, set()).add(host)
        for field in fields[1:]:
            if field.startswith("ansible_host="):
                host_addresses[host] = field.split("=", 1)[1]

    return host_addresses, groups


def normalize_boolean(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def ssh_identity_is_pinned(registry: Path, host: str, address: str) -> bool:
    expected_aliases = {host, f"{host}.intern", address}
    for raw_line in registry.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) < 3 or fields[1] != "ssh-ed25519":
            continue
        if expected_aliases <= set(fields[0].split(",")):
            return True
    return False


def _target_eval_expression() -> str:
    return """c: {
      hostname = c.networking.hostName;
      centerKey = c.roles.endoreg-client.defaultCenterKey;
      vault = {
        enable = c.luxnix.vault.enable;
        clientEnable = c.luxnix.vault.client.enable;
        address = c.luxnix.vault.client.address;
        caFile = c.luxnix.vault.client.caCertFile;
        authMethod = c.luxnix.vault.client.auth.method;
        roleIdFile = c.luxnix.vault.client.auth.roleIdFile;
        secretIdFile = c.luxnix.vault.client.auth.secretIdFile;
        deferUntilProvisioned = c.luxnix.vault.client.auth.deferUntilProvisioned;
        hubPkiEnable = c.luxnix.vault.client.hubPki.enable;
      };
      transfer = {
        enable = c.services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable;
        requireMtls =
          c.services.luxnix.lxAnnotateLocal.hub.outboundTransfer.requireMtls;
        caFile = c.services.luxnix.lxAnnotateLocal.hub.outboundTransfer.caFile;
      };
    }"""


def inspect_repository(
    repository: Path,
    host: str,
    runner: RunCommand = run_command,
) -> dict[str, object]:
    checks: list[CheckResult] = []

    def record(check_id: str, passed: bool, detail: str) -> None:
        checks.append(CheckResult(check_id, "pass" if passed else "fail", detail))

    repository = repository.resolve()
    inventory_path = repository / "ansible/inventory/hosts.ini"
    host_vars_path = repository / f"ansible/inventory/host_vars/{host}.yml"
    group_vars_path = repository / "ansible/inventory/group_vars/gpu_client.yml"
    generated_path = repository / f"systems/x86_64-linux/{host}/default.nix"
    ssh_registry = repository / "conf/ssh-host-keys/known_hosts"

    required_paths = [
        inventory_path,
        host_vars_path,
        group_vars_path,
        generated_path,
        ssh_registry,
    ]
    missing_paths = [
        path.relative_to(repository).as_posix()
        for path in required_paths
        if not path.is_file()
    ]
    record(
        "repository.paths",
        not missing_paths,
        "all canonical inputs exist"
        if not missing_paths
        else f"missing: {', '.join(missing_paths)}",
    )

    revision: str | None = None
    branch: str | None = None
    try:
        root = Path(
            runner(["git", "rev-parse", "--show-toplevel"], repository)
        ).resolve()
        revision = runner(["git", "rev-parse", "HEAD"], repository)
        branch = runner(["git", "branch", "--show-current"], repository) or "detached"
        record("source.root", root == repository, f"deployment source: {root}")
        dirty_lines = runner(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            repository,
        ).splitlines()
        record(
            "source.clean",
            not dirty_lines,
            "worktree is clean"
            if not dirty_lines
            else f"worktree has {len(dirty_lines)} changed path(s)",
        )
    except RuntimeError as error:
        record("source.git", False, str(error))

    address = ""
    if inventory_path.is_file():
        try:
            host_addresses, groups = parse_inventory(inventory_path)
            address = host_addresses.get(host, "")
            record(
                "inventory.host",
                bool(address),
                "exact host has an ansible_host address",
            )
            missing_groups = sorted(
                group
                for group in REQUIRED_GROUPS
                if host not in groups.get(group, set())
            )
            record(
                "inventory.groups",
                not missing_groups,
                "required site groups are present"
                if not missing_groups
                else f"missing groups: {', '.join(missing_groups)}",
            )
            try:
                ipaddress.ip_address(address)
                address_valid = True
            except ValueError:
                address_valid = False
            record(
                "inventory.address", address_valid, "inventory address is a literal IP"
            )
        except (OSError, ValueError) as error:
            record("inventory.parse", False, f"inventory could not be parsed: {error}")

    host_defer: bool | None = None
    if host_vars_path.is_file():
        try:
            host_vars = yaml_mapping(host_vars_path)
            configured_source = host_vars.get("luxnix_dev_repo")
            record(
                "source.host_contract",
                configured_source == str(repository),
                "host deployment source matches this checkout"
                if configured_source == str(repository)
                else "host deployment source does not match this checkout",
            )
            host_luxnix = host_vars.get("host_luxnix")
            raw_defer = (
                host_luxnix.get("vault.client.auth.deferUntilProvisioned")
                if isinstance(host_luxnix, dict)
                else None
            )
            host_defer = normalize_boolean(raw_defer)
            record(
                "enrollment.host_state",
                host_defer is not None,
                f"host-scoped defer state is {str(host_defer).lower()}"
                if host_defer is not None
                else "host-scoped defer state is missing or invalid",
            )
        except (OSError, ValueError) as error:
            record(
                "host_vars.parse", False, f"host variables could not be parsed: {error}"
            )

    if group_vars_path.is_file():
        try:
            group_vars = yaml_mapping(group_vars_path)
            group_luxnix = group_vars.get("group_luxnix")
            shared_defer = (
                isinstance(group_luxnix, dict)
                and "vault.client.auth.deferUntilProvisioned" in group_luxnix
            )
            record(
                "enrollment.fleet_scope",
                not shared_defer,
                "temporary defer state is not fleet-wide"
                if not shared_defer
                else "gpu_client group contains the temporary defer state",
            )
        except (OSError, ValueError) as error:
            record(
                "group_vars.parse",
                False,
                f"GPU client variables could not be parsed: {error}",
            )

    if ssh_registry.is_file() and address:
        record(
            "ssh.identity",
            ssh_identity_is_pinned(ssh_registry, host, address),
            "ed25519 identity pins hostname, FQDN, and inventory IP",
        )

    target_config: dict[str, Any] | None = None
    if generated_path.is_file():
        try:
            output = runner(
                [
                    "nix",
                    "eval",
                    "--json",
                    f".#nixosConfigurations.{host}.config",
                    "--apply",
                    _target_eval_expression(),
                ],
                repository,
            )
            parsed = json.loads(output)
            target_config = parsed if isinstance(parsed, dict) else None
            record(
                "nix.target_eval",
                target_config is not None,
                "target configuration evaluates",
            )
        except (RuntimeError, json.JSONDecodeError) as error:
            record("nix.target_eval", False, f"target evaluation failed: {error}")

    center_key: str | None = None
    if target_config is not None:
        vault = target_config.get("vault")
        transfer = target_config.get("transfer")
        center_key_value = target_config.get("centerKey")
        center_key = (
            center_key_value
            if isinstance(center_key_value, str) and center_key_value
            else None
        )
        vault_expected = {
            "enable": True,
            "clientEnable": True,
            "address": "https://vault.endo-reg.net:8200",
            "caFile": "/etc/secrets/vault/hub-pki/vault-server-ca.pem",
            "authMethod": "approle",
            "roleIdFile": "/etc/secrets/vault/hub-pki/approle_role_id",
            "secretIdFile": "/etc/secrets/vault/hub-pki/approle_secret_id",
            "deferUntilProvisioned": host_defer,
            "hubPkiEnable": True,
        }
        transfer_expected = {
            "enable": True,
            "requireMtls": True,
            "caFile": "/etc/secrets/vault/hub-pki/vault-server-ca.pem",
        }
        record(
            "nix.target_identity",
            target_config.get("hostname") == host and center_key is not None,
            "evaluated hostname and immutable center key are present",
        )
        record(
            "nix.vault_contract",
            vault == vault_expected,
            "Vault AppRole and PKI contract matches",
        )
        record(
            "nix.transfer_contract",
            transfer == transfer_expected,
            "outbound transfer requires mTLS",
        )

    try:
        receiver_output = runner(
            [
                "nix",
                "eval",
                "--json",
                ".#nixosConfigurations.gs-02.config.services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes",
            ],
            repository,
        )
        receiver_nodes = json.loads(receiver_output)
        matches = [
            node
            for node in receiver_nodes
            if isinstance(node, dict) and node.get("nodeKey") == host
        ]
        receiver_ok = (
            len(matches) == 1
            and matches[0].get("role") == "site_node"
            and matches[0].get("centerKey") == center_key
            and matches[0].get("sharedSecretFile")
            == f"/etc/secrets/vault/hub-pki/{host}-source-node-secret"
        )
        record(
            "nix.receiver_contract",
            receiver_ok,
            "gs-02 has one matching site receiver identity",
        )
    except (RuntimeError, json.JSONDecodeError, TypeError) as error:
        record("nix.receiver_contract", False, f"receiver evaluation failed: {error}")

    ready = all(check.status == "pass" for check in checks)
    return {
        "schema_version": "1.0",
        "host": host,
        "repository": str(repository),
        "revision": revision,
        "branch": branch,
        "ready": ready,
        "checks": [asdict(check) for check in checks],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate non-secret prerequisites for one Vault site enrollment."
    )
    parser.add_argument(
        "host", help="Exact inventory hostname; groups are not accepted"
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="Reviewed LuxNix deployment checkout (default: current directory)",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    args = parser.parse_args(argv)
    if not HOST_PATTERN.fullmatch(args.host):
        parser.error("host must be one lowercase inventory hostname")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = inspect_repository(args.repository, args.host)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Vault site enrollment preflight: {report['host']}")
        print(f"Source: {report['repository']} @ {report['revision'] or 'unknown'}")
        for check in cast(list[dict[str, str]], report["checks"]):
            print(f"{check['status'].upper():4} {check['id']}: {check['detail']}")
        print("READY" if report["ready"] else "NOT READY")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
