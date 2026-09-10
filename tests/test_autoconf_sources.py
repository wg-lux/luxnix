import json

import pytest

from lx_administration.autoconf.errors import (
    AutoconfSourceError,
    AutoconfYamlError,
)
from lx_administration.autoconf.imports.ansible_facts import (
    AnsibleFactFormatError,
    import_ansible_facts,
    load_all_host_facts,
)
from lx_administration.autoconf.imports.merge import deep_update
from lx_administration.autoconf.imports.sources import (
    load_group_vars,
    load_home_host_vars,
    load_host_vars,
    load_roles,
)


def test_fact_loader_accepts_a_missing_optional_snapshot_directory(tmp_path):
    facts_dir = tmp_path / "missing-cmdb"

    assert load_all_host_facts(facts_dir) == {}


def test_fact_loader_accepts_raw_and_normalized_setup_responses(tmp_path):
    result = {
        "ansible_facts": {
            "ansible_machine": "x86_64",
            "ansible_all_ipv4_addresses": ["10.20.30.4"],
        }
    }
    raw_snapshot = tmp_path / "raw.json"
    normalized_snapshot = tmp_path / "normalized.json"
    raw_snapshot.write_text(json.dumps(result))
    normalized_snapshot.write_text(json.dumps({"node.example": [result]}))

    assert import_ansible_facts(raw_snapshot) == import_ansible_facts(
        normalized_snapshot
    )


@pytest.mark.parametrize(
    "snapshot",
    ({}, {"node": []}, {"node": [{"failed": True, "ansible_facts": {}}]}),
)
def test_fact_loader_rejects_invalid_setup_responses(tmp_path, snapshot):
    fact_file = tmp_path / "node.json"
    fact_file.write_text(json.dumps(snapshot))

    with pytest.raises(AnsibleFactFormatError, match="node.json"):
        import_ansible_facts(fact_file)


@pytest.mark.parametrize(
    "facts",
    (
        {"ansible_date_time": "invalid"},
        {"ansible_default_ipv4": []},
    ),
)
def test_fact_loader_rejects_non_mapping_nested_facts(tmp_path, facts):
    fact_file = tmp_path / "node.json"
    fact_file.write_text(json.dumps({"ansible_facts": facts}))

    with pytest.raises(AnsibleFactFormatError, match="node.json"):
        import_ansible_facts(fact_file)


def test_fact_loader_does_not_expose_invalid_fact_values(tmp_path):
    fact_file = tmp_path / "node.json"
    fact_file.write_text(
        json.dumps(
            {
                "ansible_facts": {
                    "ansible_all_ipv4_addresses": [{"token": "TOP_SECRET_FACT_VALUE"}]
                }
            }
        )
    )

    with pytest.raises(AnsibleFactFormatError) as error:
        import_ansible_facts(fact_file)

    assert str(error.value) == "Invalid Ansible fact snapshot values: node.json"
    assert "TOP_SECRET_FACT_VALUE" not in str(error.value)


def test_fact_loader_does_not_expose_invalid_snapshot_contents(tmp_path):
    fact_file = tmp_path / "node.json"
    fact_file.write_text('{"secret": "TOP_SECRET"')

    with pytest.raises(AnsibleFactFormatError) as error:
        import_ansible_facts(fact_file)

    assert str(error.value) == "Invalid JSON in Ansible fact snapshot: node.json"
    assert "TOP_SECRET" not in str(error.value)


def test_fact_loader_preserves_dotted_hostnames_and_orders_snapshots(tmp_path):
    result = {"ansible_facts": {"ansible_machine": "x86_64"}}
    (tmp_path / "zeta.json").write_text(json.dumps(result))
    (tmp_path / "alpha.example.json").write_text(json.dumps(result))

    assert list(load_all_host_facts(tmp_path)) == ["alpha.example", "zeta"]


def test_host_var_loader_excludes_the_home_subtree(tmp_path):
    host_vars_dir = tmp_path / "host_vars"
    (host_vars_dir / "home").mkdir(parents=True)
    (host_vars_dir / "node.yml").write_text("host_nixos:\n  enabled: true\n")
    (host_vars_dir / "home/node.yml").write_text(
        "host_nixos:\n  leaked_from_home: true\n"
    )

    assert load_host_vars(host_vars_dir) == {"node": {"host_nixos": {"enabled": True}}}


def test_variable_loaders_accept_both_yaml_filename_suffixes(tmp_path) -> None:
    inventory_dir = tmp_path / "inventory"
    group_vars_dir = inventory_dir / "group_vars"
    host_vars_dir = inventory_dir / "host_vars"
    home_vars_dir = host_vars_dir / "home"
    group_vars_dir.mkdir(parents=True)
    home_vars_dir.mkdir(parents=True)

    (group_vars_dir / "service.yaml").write_text("group: yaml\n")
    (host_vars_dir / "node.yaml").write_text("host: yaml\n")
    (group_vars_dir / "group_home_shared.yaml").write_text("home:\n  group: yaml\n")
    (home_vars_dir / "home-node.yaml").write_text("home:\n  host: yaml\n")
    (inventory_dir / "home-hosts.yml").write_text(
        """schema_version: 1
default_groups:
  - group_home_shared
hosts:
  home-node: {}
""",
        encoding="utf-8",
    )

    assert load_group_vars(group_vars_dir)["service"] == {"group": "yaml"}
    assert load_host_vars(host_vars_dir) == {"node": {"host": "yaml"}}
    assert load_home_host_vars(inventory_dir) == {
        "home-node": {"home": {"group": "yaml", "host": "yaml"}}
    }


@pytest.mark.parametrize("source_kind", ("group", "host", "home"))
def test_variable_loaders_reject_ambiguous_yaml_suffix_variants(
    tmp_path,
    source_kind,
) -> None:
    inventory_dir = tmp_path / "inventory"
    if source_kind == "group":
        source_dir = inventory_dir / "group_vars"
        source_dir.mkdir(parents=True)
    elif source_kind == "host":
        source_dir = inventory_dir / "host_vars"
        source_dir.mkdir(parents=True)
    else:
        source_dir = inventory_dir / "host_vars/home"
        source_dir.mkdir(parents=True)
        (inventory_dir / "home-hosts.yml").write_text(
            "schema_version: 1\nhosts:\n  node: {}\n",
            encoding="utf-8",
        )

    (source_dir / "node.yml").write_text("format: yml\n")
    (source_dir / "node.yaml").write_text("format: yaml\n")

    with pytest.raises(AutoconfSourceError, match="Ambiguous .* YAML source.*node"):
        if source_kind == "group":
            load_group_vars(source_dir)
        elif source_kind == "host":
            load_host_vars(source_dir)
        else:
            load_home_host_vars(inventory_dir)


def test_role_loader_accepts_optional_vars_and_both_yaml_suffixes(tmp_path) -> None:
    roles_dir = tmp_path / "roles"
    (roles_dir / "files-only/files").mkdir(parents=True)
    (roles_dir / "files-only/files/payload").write_text("content\n")
    (roles_dir / "configured/vars").mkdir(parents=True)
    (roles_dir / "configured/vars/main.yaml").write_text(
        "configured_enabled: true\nkeep_configured_enabled: true\n",
        encoding="utf-8",
    )

    roles = load_roles(roles_dir)

    assert roles["files-only"]["vars"] == {}
    assert [path.name for path in roles["files-only"]["files"]] == ["payload"]
    assert roles["configured"]["vars"] == {
        "role_enabled": True,
        "keep_configured_enabled": True,
    }


def test_role_loader_rejects_ambiguous_main_yaml_variants(tmp_path) -> None:
    vars_dir = tmp_path / "roles/service/vars"
    vars_dir.mkdir(parents=True)
    (vars_dir / "main.yml").write_text("service_enabled: true\n")
    (vars_dir / "main.yaml").write_text("service_enabled: false\n")

    with pytest.raises(
        AutoconfSourceError,
        match="Ambiguous role 'service' variables YAML source.*main",
    ):
        load_roles(tmp_path / "roles")


def test_home_var_loader_accepts_an_empty_manifest_without_a_home_subtree(
    tmp_path,
) -> None:
    inventory_dir = tmp_path / "inventory"
    inventory_dir.mkdir()
    (inventory_dir / "home-hosts.yml").write_text(
        "schema_version: 1\nhosts: {}\n",
        encoding="utf-8",
    )

    assert load_home_host_vars(inventory_dir) == {}


def test_home_var_loader_names_configured_hosts_missing_variable_files(
    tmp_path,
) -> None:
    inventory_dir = tmp_path / "inventory"
    inventory_dir.mkdir()
    (inventory_dir / "home-hosts.yml").write_text(
        "schema_version: 1\nhosts:\n  node-01: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        AutoconfSourceError,
        match="home host sources disagree \\(missing host vars: node-01\\)",
    ):
        load_home_host_vars(inventory_dir)


@pytest.mark.parametrize(
    ("directory_name", "loader"),
    (
        ("group_vars", load_group_vars),
        ("host_vars", load_host_vars),
    ),
)
def test_inventory_var_loaders_wrap_duplicate_keys_with_safe_path(
    tmp_path, directory_name, loader
):
    variables_dir = tmp_path / directory_name
    variables_dir.mkdir()
    source = variables_dir / "node.yml"
    source.write_text("settings:\n  port: 1\n  port: 2\n", encoding="utf-8")

    with pytest.raises(AutoconfYamlError, match="Invalid YAML") as error:
        loader(variables_dir)

    assert str(source) in str(error.value)


def test_home_var_loader_has_documented_stable_precedence(tmp_path):
    inventory_dir = tmp_path / "inventory"
    group_vars_dir = inventory_dir / "group_vars"
    home_vars_dir = inventory_dir / "host_vars/home"
    group_vars_dir.mkdir(parents=True)
    home_vars_dir.mkdir(parents=True)
    (inventory_dir / "home-hosts.yml").write_text("""schema_version: 1
default_groups:
  - group_home_alpha
  - group_home_zeta
hosts:
  NodeA: {}
""")
    (group_vars_dir / "group_home_zeta.yml").write_text(
        "home:\n  precedence: zeta\n  zeta: true\n"
    )
    (group_vars_dir / "group_home_alpha.yml").write_text(
        "home:\n  precedence: alpha\n  alpha: true\n"
    )
    (home_vars_dir / "NodeA.yml").write_text("home:\n  precedence: host\n")

    assert load_home_host_vars(inventory_dir) == {
        "NodeA": {
            "home": {
                "precedence": "host",
                "alpha": True,
                "zeta": True,
            }
        }
    }


def test_deep_update_does_not_mutate_its_inputs():
    base = {"nested": {"left": 1}, "unchanged": True}
    updates = {"nested": {"right": 2}}

    assert deep_update(base, updates) == {
        "nested": {"left": 1, "right": 2},
        "unchanged": True,
    }
    assert base == {"nested": {"left": 1}, "unchanged": True}
    assert updates == {"nested": {"right": 2}}


def test_deep_update_rejects_non_string_nested_keys():
    with pytest.raises(
        AutoconfSourceError,
        match="Updated nested configuration must use string keys",
    ):
        deep_update({"nested": {}}, {"nested": {1: "invalid"}})


def test_group_var_loader_merges_split_group_files_in_filename_order(tmp_path):
    group_dir = tmp_path / "all"
    group_dir.mkdir()
    (group_dir / "20-second.yml").write_text(
        "nested:\n  precedence: second\n  right: true\n"
    )
    (group_dir / "10-first.yml").write_text(
        "nested:\n  precedence: first\n  left: true\n"
    )

    assert load_group_vars(tmp_path) == {
        "all": {
            "nested": {
                "precedence": "second",
                "left": True,
                "right": True,
            }
        }
    }


def test_group_var_loader_rejects_file_and_directory_for_the_same_group(tmp_path):
    (tmp_path / "all.yml").write_text("enabled: true\n")
    (tmp_path / "all").mkdir()

    with pytest.raises(ValueError, match="both file and directory.*all"):
        load_group_vars(tmp_path)
