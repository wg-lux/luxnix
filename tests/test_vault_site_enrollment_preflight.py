from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "vault"
    / "site_enrollment_preflight.py"
)


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("site_enrollment_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def prepare_repository(tmp_path: Path) -> Path:
    files = {
        "ansible/inventory/hosts.ini": """
[all]
gs-02 ansible_host=172.16.255.22
gc-10 ansible_host=172.16.255.110

[active_clients]
gc-10

[gpu_client]
gc-10

[endoreg_client]
gc-10
""",
        "ansible/inventory/group_vars/gpu_client.yml": """
group_luxnix:
  vault.client.auth.method: '"approle"'
""",
        "conf/ssh-host-keys/known_hosts": (
            "gc-10,gc-10.intern,172.16.255.110 ssh-ed25519 synthetic-public-key\n"
        ),
        "systems/x86_64-linux/gc-10/default.nix": "{ ... }: {}\n",
    }
    for relative_path, content in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")

    host_vars = tmp_path / "ansible/inventory/host_vars/gc-10.yml"
    host_vars.parent.mkdir(parents=True, exist_ok=True)
    host_vars.write_text(
        "\n".join(
            [
                f'luxnix_dev_repo: "{tmp_path}"',
                "host_luxnix:",
                '  vault.client.auth.deferUntilProvisioned: "true"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def successful_runner(
    repository: Path, *, dirty: bool = False, receiver_center: str = "center-a"
):
    target = {
        "hostname": "gc-10",
        "centerKey": "center-a",
        "vault": {
            "enable": True,
            "clientEnable": True,
            "address": "https://vault.endo-reg.net:8200",
            "caFile": "/etc/secrets/vault/hub-pki/vault-server-ca.pem",
            "authMethod": "approle",
            "roleIdFile": "/etc/secrets/vault/hub-pki/approle_role_id",
            "secretIdFile": "/etc/secrets/vault/hub-pki/approle_secret_id",
            "deferUntilProvisioned": True,
            "hubPkiEnable": True,
        },
        "transfer": {
            "enable": True,
            "requireMtls": True,
            "caFile": "/etc/secrets/vault/hub-pki/vault-server-ca.pem",
        },
    }
    receiver = [
        {
            "nodeKey": "gc-10",
            "role": "site_node",
            "centerKey": receiver_center,
            "sharedSecretFile": "/etc/secrets/vault/hub-pki/gc-10-source-node-secret",
        }
    ]

    def runner(command: list[str], cwd: Path) -> str:
        assert cwd == repository
        if command[:3] == ["git", "rev-parse", "--show-toplevel"]:
            return str(repository)
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return "a" * 40
        if command[:3] == ["git", "branch", "--show-current"]:
            return "release"
        if command[:3] == ["git", "status", "--porcelain=v1"]:
            return " M unrelated.nix" if dirty else ""
        if command[0:3] == ["nix", "eval", "--json"]:
            if command[3].startswith(".#nixosConfigurations.gc-10"):
                return json.dumps(target)
            if command[3].startswith(".#nixosConfigurations.gs-02"):
                return json.dumps(receiver)
        raise AssertionError(f"unexpected command: {command}")

    return runner


def checks_by_id(report: dict[str, object]) -> dict[str, dict[str, str]]:
    return {
        check["id"]: check
        for check in report["checks"]  # type: ignore[union-attr]
    }


def test_ready_site_passes_every_non_secret_gate(tmp_path: Path) -> None:
    module = load_script()
    repository = prepare_repository(tmp_path)

    report = module.inspect_repository(
        repository,
        "gc-10",
        successful_runner(repository),
    )

    assert report["ready"] is True
    assert report["host"] == "gc-10"
    assert report["revision"] == "a" * 40
    assert all(check["status"] == "pass" for check in report["checks"])
    serialized = json.dumps(report)
    assert "synthetic-public-key" not in serialized
    assert "secret_id" not in serialized


def test_dirty_source_and_receiver_mismatch_fail_closed(tmp_path: Path) -> None:
    module = load_script()
    repository = prepare_repository(tmp_path)

    report = module.inspect_repository(
        repository,
        "gc-10",
        successful_runner(repository, dirty=True, receiver_center="wrong-center"),
    )
    checks = checks_by_id(report)

    assert report["ready"] is False
    assert checks["source.clean"]["status"] == "fail"
    assert checks["nix.receiver_contract"]["status"] == "fail"


def test_fleet_wide_defer_and_unpinned_identity_fail_closed(tmp_path: Path) -> None:
    module = load_script()
    repository = prepare_repository(tmp_path)
    (repository / "ansible/inventory/group_vars/gpu_client.yml").write_text(
        'group_luxnix:\n  vault.client.auth.deferUntilProvisioned: "true"\n',
        encoding="utf-8",
    )
    (repository / "conf/ssh-host-keys/known_hosts").write_text(
        "gc-10 ssh-ed25519 synthetic-public-key\n",
        encoding="utf-8",
    )

    report = module.inspect_repository(
        repository,
        "gc-10",
        successful_runner(repository),
    )
    checks = checks_by_id(report)

    assert report["ready"] is False
    assert checks["enrollment.fleet_scope"]["status"] == "fail"
    assert checks["ssh.identity"]["status"] == "fail"


def test_inventory_group_name_is_not_accepted_as_a_host(tmp_path: Path) -> None:
    module = load_script()
    repository = prepare_repository(tmp_path)

    report = module.inspect_repository(
        repository,
        "gpu-client",
        successful_runner(repository),
    )
    checks = checks_by_id(report)

    assert report["ready"] is False
    assert checks["repository.paths"]["status"] == "fail"
    assert checks["inventory.host"]["status"] == "fail"
