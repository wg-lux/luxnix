import shutil
from pathlib import Path

import pytest
import yaml

from lx_administration.autoconf.config import (
    AUTOCONF_OPTION_NAMES,
    DEFAULT_CONFIG_PATH,
    AutoconfConfig,
    AutoconfConfigError,
)
from tests.autoconf_test_support import write_config

REPO_ROOT = Path(__file__).parents[1]


def test_autoconf_config_resolves_paths_relative_to_config(tmp_path):
    config = AutoconfConfig.load(write_config(tmp_path))

    assert config.ansible_root == tmp_path / "ansible"
    assert config.output == tmp_path / "generated"
    assert config.nix_output == tmp_path / "output"
    assert config.nix_templates == tmp_path / "templates"
    assert config.report_output == tmp_path / "report/index.html"
    assert config.facts_dir == tmp_path / "ansible/cmdb"
    assert config.inventory_subnet == "10.20.30."
    assert config.inventory_system_group == "active_clients"
    assert config.home_default_users == ("operator",)
    assert config.home_state_version == "23.11"
    assert config.validation_errors() == []


def test_autoconf_config_allows_missing_generated_nix_output(tmp_path) -> None:
    config = AutoconfConfig.load(write_config(tmp_path))
    shutil.rmtree(config.nix_output)

    config.require_valid()

    assert config.validation_errors() == []


def test_autoconf_config_allows_missing_optional_fact_snapshots(tmp_path) -> None:
    config = AutoconfConfig.load(write_config(tmp_path))
    shutil.rmtree(config.facts_dir)

    config.require_valid()

    assert config.validation_errors() == []


def test_autoconf_config_allows_no_home_host_variable_directory(tmp_path) -> None:
    config = AutoconfConfig.load(write_config(tmp_path))
    shutil.rmtree(config.source_layout.inventory.home_vars_dir)

    config.require_valid()

    assert config.validation_errors() == []


def test_autoconf_config_allows_no_home_template_directory(tmp_path) -> None:
    config = AutoconfConfig.load(write_config(tmp_path))
    shutil.rmtree(config.template_layout.homes_dir)

    config.require_valid()

    assert config.validation_errors() == []


def test_pipeline_validates_home_sources_before_creating_output(tmp_path) -> None:
    from lx_administration.autoconf import run_from_config

    config = AutoconfConfig.load(write_config(tmp_path))
    (tmp_path / "ansible/inventory/home-hosts.yml").unlink()

    with pytest.raises(AutoconfConfigError, match="Home Manager host manifest"):
        run_from_config(config)

    assert not config.output.exists()


def test_autoconf_config_reads_options_by_canonical_name(tmp_path):
    config = AutoconfConfig.load(write_config(tmp_path))

    assert config.get_option("paths.ansible_root") == tmp_path / "ansible"
    assert config.get_option("inventory.subnet") == "10.20.30."
    assert config.get_option("home.default_users") == "operator"


def test_autoconf_config_rejects_unknown_programmatic_option(tmp_path):
    config = AutoconfConfig.load(write_config(tmp_path))

    with pytest.raises(AutoconfConfigError, match="Unknown autoconf option 'missing'"):
        config.get_option("missing")


def test_default_autoconf_config_is_independent_of_working_directory(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)

    config = AutoconfConfig.load()

    assert config.source == DEFAULT_CONFIG_PATH
    assert config.source == REPO_ROOT / "autoconf/config.yml"


def test_autoconf_local_artifact_paths_match_the_project_map() -> None:
    config = AutoconfConfig.load()
    project_paths = yaml.safe_load(
        (REPO_ROOT / "luxnix.yml").read_text(encoding="utf-8")
    )["paths"]

    assert config.facts_dir == REPO_ROOT / project_paths["local_ansible_facts"]
    assert config.report_output == REPO_ROOT / project_paths["local_inventory_report"]
    assert config.log_dir == config.output_layout.log_dir


@pytest.mark.parametrize("subnet", ["10.20.30.0", "10.20.", "10.20.nope."])
def test_autoconf_config_rejects_invalid_subnet(tmp_path, subnet):
    config_file = write_config(tmp_path)
    config_file.write_text(config_file.read_text().replace("10.20.30.", subnet))

    with pytest.raises(AutoconfConfigError, match="inventory.subnet"):
        AutoconfConfig.load(config_file)


def test_autoconf_config_rejects_unknown_options(tmp_path):
    config_file = write_config(tmp_path, "unexpected: true\n")

    with pytest.raises(AutoconfConfigError, match="Unknown option.*unexpected"):
        AutoconfConfig.load(config_file)


def test_autoconf_config_rejects_non_string_option_names(tmp_path):
    config_file = write_config(tmp_path)
    config_file.write_text(
        config_file.read_text(encoding="utf-8") + "1: unexpected\n",
        encoding="utf-8",
    )

    with pytest.raises(AutoconfConfigError, match="'root' keys must be strings"):
        AutoconfConfig.load(config_file)


@pytest.mark.parametrize("option", AUTOCONF_OPTION_NAMES)
def test_autoconf_config_requires_every_canonical_option(tmp_path, option):
    config_file = write_config(tmp_path)
    config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    section, key = option.split(".", maxsplit=1)
    del config[section][key]
    config_file.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(
        AutoconfConfigError,
        match=rf"Missing option.*'{section}'.*{key}",
    ):
        AutoconfConfig.load(config_file)


@pytest.mark.parametrize(
    "duplicate",
    (
        "schema_version: 1\n",
        "paths:\n  output: shadowed\n",
    ),
)
def test_autoconf_config_rejects_duplicate_options(tmp_path, duplicate):
    config_file = write_config(tmp_path, duplicate)

    with pytest.raises(AutoconfConfigError, match="duplicate key"):
        AutoconfConfig.load(config_file)


@pytest.mark.parametrize(
    "value",
    ("[]", "[admin, admin]", "[admin, '']", "admin"),
)
def test_autoconf_config_rejects_invalid_default_home_users(tmp_path, value):
    config_file = write_config(tmp_path)
    config_file.write_text(
        config_file.read_text().replace(
            "default_users:\n    - operator", f"default_users: {value}"
        )
    )

    with pytest.raises(AutoconfConfigError, match="home.default_users"):
        AutoconfConfig.load(config_file)


@pytest.mark.parametrize("value", ("23.11", '"current"', '"23"', '"2023.11"'))
def test_autoconf_config_rejects_invalid_home_state_version(tmp_path, value):
    config_file = write_config(tmp_path)
    config_file.write_text(
        config_file.read_text().replace(
            'state_version: "23.11"', f"state_version: {value}"
        )
    )

    with pytest.raises(AutoconfConfigError, match="home.state_version"):
        AutoconfConfig.load(config_file)
