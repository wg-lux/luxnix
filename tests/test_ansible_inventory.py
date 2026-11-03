from __future__ import annotations

import importlib
from unittest.mock import Mock

import pytest

from lx_administration.models.ansible.inventory import AnsibleInventory


def test_inventory_host_has_no_implicit_managed_subnet() -> None:
    inventory_module = importlib.import_module(
        "lx_administration.models.ansible.inventory"
    )
    host = inventory_module.AnsibleInventoryHost(
        hostname="node-01",
        ansible_host="10.20.30.4",
    )

    assert host.subnet is None
    with pytest.raises(ValueError, match="subnet is required"):
        host.validate_ansible_host()


def test_inventory_loader_rejects_invalid_explicit_subnet(tmp_path) -> None:
    hosts_file = tmp_path / "hosts.ini"
    hosts_file.write_text("[all]\nnode-01 ansible_host=10.20.30.4\n")

    with pytest.raises(ValueError, match="three-octet IPv4 prefix"):
        AnsibleInventory.load_from_hosts_ini(hosts_file, subnet="10.20.nope.")


def test_inventory_group_and_role_names_use_exact_identity() -> None:
    inventory_module = importlib.import_module(
        "lx_administration.models.ansible.inventory"
    )
    inventory = AnsibleInventory(
        groups=[inventory_module.AnsibleInventoryGroup(name="active_clients")],
        roles=[inventory_module.AnsibleInventoryRole(name="ssl_cert")],
    )

    assert inventory.group_name_exists("active_clients")
    assert inventory.role_name_exists("ssl_cert")
    assert not inventory.group_name_exists("active")
    assert not inventory.role_name_exists("ssl")

    with pytest.raises(ValueError, match="Unknown inventory group 'active'"):
        inventory.get_group_by_name("active", logger=Mock())
    with pytest.raises(ValueError, match="Unknown inventory role 'ssl'"):
        inventory.get_role_by_name("ssl", logger=Mock())

    assert inventory.get_group_names() == ["active_clients"]
    assert inventory.get_role_names() == ["ssl_cert"]


def test_inventory_name_lookup_rejects_duplicate_exact_names() -> None:
    inventory_module = importlib.import_module(
        "lx_administration.models.ansible.inventory"
    )
    inventory = AnsibleInventory(
        groups=[
            inventory_module.AnsibleInventoryGroup(name="duplicate"),
            inventory_module.AnsibleInventoryGroup(name="duplicate"),
        ]
    )

    with pytest.raises(ValueError, match="Multiple groups found with name duplicate"):
        inventory.get_group_by_name("duplicate", logger=Mock())


def test_inventory_membership_deduplication_preserves_precedence_order() -> None:
    inventory = AnsibleInventory()
    inventory.add_host_by_name("node-01")

    for group_name in ("all", "base", "override", "base"):
        inventory.add_group_to_host("node-01", group_name)
    for role_name in ("common", "service", "common"):
        inventory.add_role_to_host("node-01", role_name)

    host = inventory.get_host_by_name("node-01")
    assert host is not None
    assert host.ansible_group_names == ["all", "base", "override"]
    assert host.ansible_role_names == ["common", "service"]


def test_inventory_merge_uses_declared_group_and_role_order() -> None:
    inventory_module = importlib.import_module(
        "lx_administration.models.ansible.inventory"
    )
    host = inventory_module.AnsibleInventoryHost(
        hostname="node-01",
        ansible_group_names=["base", "override", "base"],
        ansible_role_names=["common", "service", "common"],
    )
    inventory = AnsibleInventory(
        all=[host],
        groups=[
            inventory_module.AnsibleInventoryGroup(
                name="base", vars={"group_luxnix": {"source": "base"}}
            ),
            inventory_module.AnsibleInventoryGroup(
                name="override", vars={"group_luxnix": {"source": "override"}}
            ),
        ],
        roles=[
            inventory_module.AnsibleInventoryRole(
                name="common", vars={"role_luxnix": {"source": "common"}}
            ),
            inventory_module.AnsibleInventoryRole(
                name="service", vars={"role_luxnix": {"source": "service"}}
            ),
        ],
    )

    merged = inventory.export_merged_host_vars("node-01")
    group_luxnix = merged["group_luxnix"]
    role_luxnix = merged["role_luxnix"]

    assert isinstance(group_luxnix, dict)
    assert isinstance(role_luxnix, dict)
    assert group_luxnix["source"] == "override"
    assert role_luxnix["source"] == "service"


def test_inventory_merge_resolves_transitive_group_and_role_dependencies() -> None:
    inventory_module = importlib.import_module(
        "lx_administration.models.ansible.inventory"
    )
    inventory = AnsibleInventory(
        all=[
            inventory_module.AnsibleInventoryHost(
                hostname="node-01",
                ansible_group_names=["base"],
                vars={"precedence": "host"},
            )
        ],
        groups=[
            inventory_module.AnsibleInventoryGroup(
                name="base",
                vars={"ansible_groups": ["shared"], "base_loaded": True},
            ),
            inventory_module.AnsibleInventoryGroup(
                name="shared",
                vars={"ansible_roles": ["service"], "shared_loaded": True},
            ),
            inventory_module.AnsibleInventoryGroup(
                name="from-role",
                vars={"role_group_loaded": True},
            ),
        ],
        roles=[
            inventory_module.AnsibleInventoryRole(
                name="service",
                vars={
                    "ansible_groups": ["from-role"],
                    "role_loaded": True,
                    "precedence": "role",
                },
            )
        ],
    )

    merged = inventory.export_merged_host_vars("node-01")

    assert merged["base_loaded"] is True
    assert merged["shared_loaded"] is True
    assert merged["role_loaded"] is True
    assert merged["role_group_loaded"] is True
    assert merged["precedence"] == "host"


@pytest.mark.parametrize(
    ("group_vars", "role_vars", "message"),
    [
        ({"ansible_roles": "service"}, {}, "group base ansible_roles"),
        ({}, {"ansible_groups": [1]}, "role service ansible_groups"),
    ],
)
def test_inventory_merge_rejects_invalid_membership_lists(
    group_vars,
    role_vars,
    message,
) -> None:
    inventory_module = importlib.import_module(
        "lx_administration.models.ansible.inventory"
    )
    inventory = AnsibleInventory(
        all=[
            inventory_module.AnsibleInventoryHost(
                hostname="node-01",
                ansible_group_names=["base"],
                ansible_role_names=["service"],
            )
        ],
        groups=[inventory_module.AnsibleInventoryGroup(name="base", vars=group_vars)],
        roles=[inventory_module.AnsibleInventoryRole(name="service", vars=role_vars)],
    )

    with pytest.raises(ValueError, match=message):
        inventory.export_merged_host_vars("node-01")


@pytest.mark.parametrize('membership,missing', [('ansible_groups', 'bas'), ('ansible_roles', 'servce')])
@pytest.mark.parametrize('source', ['host', 'group', 'role'])
def test_unknown_dependency_is_rejected_without_creating_definition(membership, missing, source):
    from lx_administration.models.ansible.inventory import (
        AnsibleInventoryGroup, AnsibleInventoryHost, AnsibleInventoryRole,
    )
    host = AnsibleInventoryHost(hostname='node-01', ansible_group_names=['base'],
                                ansible_role_names=['service'])
    group = AnsibleInventoryGroup(name='base')
    role = AnsibleInventoryRole(name='service')
    objects = {'host': host, 'group': group, 'role': role}
    objects[source].vars[membership] = [missing]
    inventory = AnsibleInventory(all=[host], groups=[group], roles=[role])
    with pytest.raises(ValueError, match='Unknown inventory'):
        inventory.export_merged_host_vars('node-01')
    assert inventory.get_group_names() == ['base']
    assert inventory.get_role_names() == ['service']


def test_loading_explicit_group_and_role_sources_creates_definitions(tmp_path):
    inventory_dir = tmp_path / 'inventory'
    group_dir = inventory_dir / 'group_vars'
    group_dir.mkdir(parents=True)
    (group_dir / 'declared.yml').write_text('group_luxnix: {enabled: true}\n')
    role_dir = inventory_dir / 'role_vars' / 'declared-role' / 'vars'
    role_dir.mkdir(parents=True)
    (role_dir / 'main.yml').write_text('role_luxnix: {enabled: true}\n')
    inventory = AnsibleInventory()
    inventory.load_group_vars(inventory_dir)
    inventory.load_role_vars(inventory_dir)
    assert inventory.get_group_by_name('declared').vars['group_luxnix']['enabled']
    assert inventory.get_role_by_name('declared-role').vars['role_luxnix']['enabled']


def test_inventory_without_all_header_loads_implicit_all_group(tmp_path):
    hosts = tmp_path / 'inventory' / 'hosts.ini'
    hosts.parent.mkdir()
    hosts.write_text('[clients]\nnode-01 ansible_host=10.20.30.4\n')
    inventory = AnsibleInventory.load_from_hosts_ini(hosts, subnet='10.20.30.')
    assert inventory.get_group_by_name('all').name == 'all'
    assert inventory.export_merged_host_vars('node-01')['group_luxnix']
