"""Reject ambiguous Nix key spellings without changing ordinary override precedence."""
import pytest

from lx_administration.models.ansible.merged_host_vars import MergedHostVars


@pytest.mark.parametrize('section', ['roles', 'services', 'luxnix', 'nixos'])
@pytest.mark.parametrize('reverse', [False, True])
def test_normalization_rejects_collisions_in_one_layer(section, reverse):
    entries = [('a_b.enable', 1), ('a-b.enable', 2)]
    config = MergedHostVars(**{'group_' + section: dict(reversed(entries) if reverse else entries)})
    with pytest.raises(ValueError, match='normalize to the same Nix key'):
        getattr(config, 'prepare_' + section)()


@pytest.mark.parametrize('section', ['roles', 'services', 'luxnix', 'nixos'])
@pytest.mark.parametrize('layers', [('group', 'role'), ('group', 'host'), ('role', 'host')])
def test_normalization_rejects_collisions_across_layers(section, layers):
    config = MergedHostVars(**{layers[0] + '_' + section: {'a_b.enable': 1},
                              layers[1] + '_' + section: {'a-b.enable': 2}})
    with pytest.raises(ValueError, match='normalize to the same Nix key'):
        getattr(config, 'prepare_' + section)()


def test_identical_spelling_keeps_group_role_host_override_precedence():
    config = MergedHostVars(group_nixos={'a_b.enable': 1},
                            role_nixos={'a_b.enable': 2}, host_nixos={'a_b.enable': 3})
    assert config.prepare_nixos() == {'a-b.enable': 3}


def test_quoted_literal_underscores_remain_distinct():
    config = MergedHostVars(group_nixos={'sysctl."a_b"': 1, 'sysctl."a-b"': 2})
    assert config.prepare_nixos() == {'sysctl."a_b"': 1, 'sysctl."a-b"': 2}


def test_canonical_inventory_hosts_resolve_without_normalization_collisions():
    from lx_administration.autoconf.config import AutoconfConfig
    from lx_administration.models.ansible.inventory import AnsibleInventory
    config = AutoconfConfig.load()
    inventory = AnsibleInventory.load_from_hosts_ini(
        config.ansible_root / 'inventory/hosts.ini', subnet=config.inventory_subnet)
    normalized = {host.hostname: MergedHostVars(
        **inventory.export_merged_host_vars(host.hostname)).export_host_config()
        for host in inventory.all}
    assert normalized['gs-02']['role_configs']['endoreg-client.enable'] == 'true'
