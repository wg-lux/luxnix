from __future__ import annotations

import ipaddress
import re
from pathlib import Path

import pytest
import yaml

from lx_administration.autoconf.config import AutoconfConfig
from lx_administration.autoconf.imports.sources import load_home_host_vars
from lx_administration.models.ansible.inventory import AnsibleInventory

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO_ROOT / "ansible/inventory/hosts.ini"


def test_inventory_defines_each_host_address_once_and_uses_valid_ips() -> None:
    inventory = INVENTORY_PATH.read_text()
    declarations = re.findall(
        r"^(\S+)\s+ansible_host=(\S+)$",
        inventory,
        re.MULTILINE,
    )
    hostnames = [hostname for hostname, _address in declarations]

    assert len(hostnames) == len(set(hostnames))
    for _hostname, address in declarations:
        ipaddress.ip_address(address)


def test_vpn_host_options_are_derived_instead_of_repeated_in_group_vars() -> None:
    group_vars = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(
            (REPO_ROOT / "ansible/inventory/group_vars/all").glob("*.yml")
        )
    )
    inventory = AnsibleInventory.load_from_hosts_ini(
        INVENTORY_PATH,
        subnet=AutoconfConfig.load().inventory_subnet,
    )
    merged = inventory.export_merged_host_vars("s-01")["group_luxnix"]

    assert ".ip_vpn:" not in group_vars
    assert merged["generic_settings.network.hosts.s_01.ip_vpn"] == '"172.16.255.1"'
    assert merged["generic_settings.network.hosts.c_01.ip_vpn"] == '"172.16.255.131"'


def test_all_group_vars_are_split_by_responsibility() -> None:
    group_vars_dir = REPO_ROOT / "ansible/inventory/group_vars"
    all_group_dir = group_vars_dir / "all"

    assert not (group_vars_dir / "all.yml").exists()
    assert {path.name for path in all_group_dir.glob("*.yml")} == {
        "10-vault.yml",
        "20-network.yml",
        "30-nix.yml",
        "40-repositories.yml",
        "50-ansible.yml",
        "60-authentication.yml",
    }


def test_inventory_rejects_a_second_vpn_address_source(tmp_path) -> None:
    inventory_dir = tmp_path / "ansible/inventory"
    group_vars_dir = inventory_dir / "group_vars"
    group_vars_dir.mkdir(parents=True)
    hosts = inventory_dir / "hosts.ini"
    hosts.write_text("[all]\nnode-01 ansible_host=10.20.30.4\n")
    (group_vars_dir / "all.yml").write_text(
        """group_luxnix:
  generic_settings.network.hosts.node_01.ip_vpn: '"10.20.30.99"'
"""
    )

    with pytest.raises(ValueError, match="derived from hosts.ini"):
        AnsibleInventory.load_from_hosts_ini(hosts, subnet="10.20.30.")


def test_h01_is_home_only_and_not_a_remote_inventory_target() -> None:
    inventory = INVENTORY_PATH.read_text()
    home_hosts = yaml.safe_load(
        (REPO_ROOT / "ansible/inventory/home-hosts.yml").read_text()
    )["hosts"]
    home_vars = load_home_host_vars(REPO_ROOT / "ansible/inventory")

    assert "h-01" not in inventory
    assert home_hosts["h-01"]["extra_groups"] == ["group_home_networking"]
    assert "h-01" in home_vars


def test_remote_inventory_contains_no_home_configuration_schema() -> None:
    inventory = INVENTORY_PATH.read_text()

    assert "[home_config]" not in inventory
    assert "[group_home_" not in inventory
    assert "[host_luxnix]" not in inventory


def test_project_map_names_both_inventory_sources() -> None:
    project = yaml.safe_load((REPO_ROOT / "luxnix.yml").read_text())

    assert project["paths"]["remote_inventory"] == "ansible/inventory/hosts.ini"
    assert project["paths"]["home_inventory"] == "ansible/inventory/home-hosts.yml"


def test_secret_role_sources_follow_the_central_repository_path() -> None:
    role_var_files = (
        REPO_ROOT / "ansible/roles/ssl_cert/vars/main.yml",
        REPO_ROOT / "ansible/roles/nginx_host/vars/main.yml",
        REPO_ROOT / "ansible/roles/smtp_cred/vars/main.yml",
    )

    for path in role_var_files:
        content = path.read_text(encoding="utf-8")
        assert "{{ luxnix_dev_repo }}/secrets/" in content
        assert "/home/admin/dev/luxnix/secrets/" not in content


def test_remote_python_interpreter_is_centralized() -> None:
    defaults = (
        REPO_ROOT / "ansible/inventory/group_vars/all/50-ansible.yml"
    ).read_text(encoding="utf-8")
    assert (
        "ansible_python_interpreter: '{{ luxnix_dest }}/.devenv/state/venv/bin/python'"
        in defaults
    )

    host_overrides = list((REPO_ROOT / "ansible/inventory/host_vars").glob("*.yml"))
    assert all(
        "ansible_python_interpreter:" not in path.read_text(encoding="utf-8")
        for path in host_overrides
    )


def test_every_system_host_directory_has_an_active_entry_point() -> None:
    systems = REPO_ROOT / "systems/x86_64-linux"
    inactive = sorted(
        path.name
        for path in systems.iterdir()
        if path.is_dir() and not (path / "default.nix").is_file()
    )

    assert not inactive, f"system host directories without default.nix: {inactive}"
    assert not list(systems.rglob("_default.nix"))
