from __future__ import annotations

import importlib
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from lx_administration.autoconf.errors import AutoconfPipelineError
from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.yaml import PRIVATE_DIRECTORY_MODE, PRIVATE_FILE_MODE

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_inventory_loader_forwards_the_pipeline_logger(monkeypatch, tmp_path) -> None:
    inventory_loader = importlib.import_module(
        "lx_administration.autoconf.imports.ansible_inventory"
    )
    pipeline_logger = Mock()
    received: dict[str, object] = {}
    expected_inventory = Mock()

    def fake_load(file, subnet, logger):
        received.update(file=file, subnet=subnet, logger=logger)
        return expected_inventory

    monkeypatch.setattr(
        inventory_loader.AnsibleInventory,
        "load_from_hosts_ini",
        fake_load,
    )
    inventory_file = tmp_path / "hosts.ini"

    inventory = inventory_loader.load_inventory_hostfile(
        inventory_file,
        subnet="10.20.30.",
        logger=pipeline_logger,
    )

    assert inventory is expected_inventory
    assert received == {
        "file": inventory_file,
        "subnet": "10.20.30.",
        "logger": pipeline_logger,
    }


def test_system_import_validates_and_serializes_inventory_once() -> None:
    pipeline_source = (
        REPO_ROOT / "lx_administration/autoconf/imports/main.py"
    ).read_text()
    artifact_source = (
        REPO_ROOT / "lx_administration/autoconf/imports/artifacts.py"
    ).read_text()
    inventory_model_source = (
        REPO_ROOT / "lx_administration/models/ansible/inventory.py"
    ).read_text()

    assert artifact_source.count("inventory.save_to_file(") == 1
    assert "inventory.validate_inventory()" not in pipeline_source
    assert "def save_to_file(" in inventory_model_source
    assert "self.validate_inventory()" in inventory_model_source


def test_home_import_fails_before_writing_partial_merged_vars(monkeypatch, tmp_path):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    written = []
    monkeypatch.setattr(
        imports_pipeline,
        "load_home_host_vars",
        lambda _path: {
            "alpha": {"group_roles": {"valid.enable": True}},
            "zeta": {"group_roles": ["invalid"]},
        },
    )
    monkeypatch.setattr(
        imports_pipeline,
        "write_merged_host_variables",
        lambda *args, **kwargs: written.append(args),
    )

    with pytest.raises(AutoconfPipelineError, match="zeta"):
        imports_pipeline.build_home_merged_variables(
            tmp_path / "ansible",
            tmp_path / "autoconf",
            logger=Mock(),
        )

    assert written == []
    assert not (tmp_path / "autoconf/home_merged_vars").exists()


def test_system_import_fails_before_writing_partial_merged_vars(monkeypatch, tmp_path):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    inventory_dir = tmp_path / "ansible/inventory"
    inventory_dir.mkdir(parents=True)
    (inventory_dir / "hosts.ini").touch()
    (tmp_path / "ansible/cmdb").mkdir()

    class Host:
        def __init__(self, hostname):
            self.hostname = hostname
            self.ansible_group_names = ["active_clients"]

        def init_ansible_role_names(self):
            return None

    class Inventory:
        all = [Host("alpha"), Host("zeta")]
        saved = False

        def hostname_update_ansible_facts(self, *_args):
            return None

        def get_group_names(self):
            return ["active_clients"]

        def export_merged_host_vars(self, hostname):
            if hostname == "zeta":
                return {"group_roles": ["invalid"]}
            return {"group_roles": {"valid.enable": True}}

        def save_to_file(self, _path, **_kwargs):
            self.saved = True

    inventory = Inventory()
    written = []
    monkeypatch.setattr(
        imports_pipeline, "load_inventory_hostfile", lambda *_args, **_kwargs: inventory
    )
    monkeypatch.setattr(imports_pipeline, "load_all_host_facts", lambda _path: {})
    monkeypatch.setattr(
        imports_pipeline,
        "write_system_intermediates",
        lambda *args, **kwargs: written.append(args),
    )

    with pytest.raises(AutoconfPipelineError, match="zeta"):
        imports_pipeline.build_system_merged_variables(
            tmp_path / "ansible",
            tmp_path / "autoconf",
            subnet="10.20.30.",
            system_group="active_clients",
            logger=Mock(),
        )

    assert inventory.saved is False
    assert written == []
    assert not (tmp_path / "autoconf/merged_vars").exists()


def test_system_import_exports_only_the_configured_system_group(monkeypatch, tmp_path):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    artifacts = importlib.import_module("lx_administration.autoconf.imports.artifacts")
    inventory_dir = tmp_path / "ansible/inventory"
    inventory_dir.mkdir(parents=True)
    (inventory_dir / "hosts.ini").touch()
    merged_vars_dir = tmp_path / "autoconf/merged_vars"
    merged_vars_dir.mkdir(parents=True)
    stale_file = merged_vars_dir / "inactive.yml"
    stale_file.touch()

    class Host:
        def __init__(self, hostname, groups):
            self.hostname = hostname
            self.ansible_group_names = groups

        def init_ansible_role_names(self):
            return None

    saved = {}

    class Inventory:
        all = [
            Host("active", ["active_clients"]),
            Host("inactive", ["all"]),
        ]

        def hostname_update_ansible_facts(self, *_args):
            return None

        def get_group_names(self):
            return ["all", "active_clients"]

        def export_merged_host_vars(self, hostname):
            return {"host_luxnix": {"selected": hostname}}

        def save_to_file(self, path, **kwargs):
            saved["path"] = path
            saved["options"] = kwargs
            path.write_text("inventory: generated\n", encoding="utf-8")

    written = []

    def record_dump(data, path, _format, **kwargs):
        written.append((data, path, kwargs))
        path.write_text("generated: true\n", encoding="utf-8")

    monkeypatch.setattr(
        imports_pipeline,
        "load_inventory_hostfile",
        lambda *_args, **_kwargs: Inventory(),
    )
    monkeypatch.setattr(imports_pipeline, "load_all_host_facts", lambda _path: {})
    monkeypatch.setattr(artifacts, "dump_yaml", record_dump)

    imports_pipeline.build_system_merged_variables(
        tmp_path / "ansible",
        tmp_path / "autoconf",
        subnet="10.20.30.",
        system_group="active_clients",
        logger=Mock(),
    )

    assert [path.name for _, path, _options in written] == ["active.yml"]
    assert written[0][0]["host_luxnix"]["selected"] == "active"
    assert written[0][2]["file_mode"] == PRIVATE_FILE_MODE
    assert saved["options"] == {"file_mode": PRIVATE_FILE_MODE}
    assert saved["path"].name == "inventory.yml"
    assert saved["path"].parent != tmp_path / "autoconf"
    assert (tmp_path / "autoconf/inventory.yml").is_file()
    assert stat.S_IMODE(merged_vars_dir.stat().st_mode) == PRIVATE_DIRECTORY_MODE
    assert (merged_vars_dir / "active.yml").is_file()
    assert not stale_file.exists()


def test_system_intermediates_preserve_previous_set_when_staging_fails(
    monkeypatch, tmp_path
):
    artifacts = importlib.import_module("lx_administration.autoconf.imports.artifacts")
    autoconf_out = tmp_path / "autoconf"
    merged_vars_dir = autoconf_out / "merged_vars"
    merged_vars_dir.mkdir(parents=True)
    inventory_file = autoconf_out / "inventory.yml"
    previous_host = merged_vars_dir / "alpha.yml"
    stale_host = merged_vars_dir / "removed-host.yml"
    inventory_file.write_text("version: previous\n", encoding="utf-8")
    previous_host.write_text("version: previous\n", encoding="utf-8")
    stale_host.write_text("version: previous\n", encoding="utf-8")

    class Inventory:
        def save_to_file(self, path, **_kwargs):
            path.write_text("version: staged\n", encoding="utf-8")

    def fail_second_dump(_data, path, _format, **_kwargs):
        path.write_text("version: staged\n", encoding="utf-8")
        if path.stem == "zeta":
            raise OSError("system staging failed")

    monkeypatch.setattr(artifacts, "dump_yaml", fail_second_dump)

    with pytest.raises(OSError, match="system staging failed"):
        artifacts.write_system_intermediates(
            Inventory(),
            autoconf_out,
            [("alpha", {}), ("zeta", {})],
        )

    assert inventory_file.read_text(encoding="utf-8") == "version: previous\n"
    assert previous_host.read_text(encoding="utf-8") == "version: previous\n"
    assert stale_host.read_text(encoding="utf-8") == "version: previous\n"
    assert not list(autoconf_out.glob(".system-intermediates.*"))


def test_home_import_writes_private_merged_variables(monkeypatch, tmp_path):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    artifacts = importlib.import_module("lx_administration.autoconf.imports.artifacts")
    monkeypatch.setattr(
        imports_pipeline,
        "load_home_host_vars",
        lambda _path: {"alpha": {"group_roles": {"valid.enable": True}}},
    )
    written = []
    output_dir = tmp_path / "autoconf/home_merged_vars"
    output_dir.mkdir(parents=True)
    stale_file = output_dir / "removed-host.yml"
    stale_file.write_text("stale: true\n", encoding="utf-8")

    def record_dump(data, path, _format, **kwargs):
        written.append((data, path, kwargs))
        path.write_text("generated: true\n", encoding="utf-8")

    monkeypatch.setattr(artifacts, "dump_yaml", record_dump)

    imports_pipeline.build_home_merged_variables(
        tmp_path / "ansible",
        tmp_path / "autoconf",
        logger=Mock(),
    )

    assert stat.S_IMODE(output_dir.stat().st_mode) == PRIVATE_DIRECTORY_MODE
    assert not stale_file.exists()
    assert len(written) == 1
    assert written[0][1].name == "alpha.yml"
    assert written[0][1].parent != output_dir
    assert written[0][2]["file_mode"] == PRIVATE_FILE_MODE
    assert (output_dir / "alpha.yml").is_file()


def test_home_import_preserves_previous_host_set_when_staging_fails(
    monkeypatch, tmp_path
):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    artifacts = importlib.import_module("lx_administration.autoconf.imports.artifacts")
    output_dir = tmp_path / "autoconf/home_merged_vars"
    output_dir.mkdir(parents=True)
    previous_alpha = output_dir / "alpha.yml"
    stale_file = output_dir / "removed-host.yml"
    previous_alpha.write_text("version: previous\n", encoding="utf-8")
    stale_file.write_text("version: previous\n", encoding="utf-8")
    monkeypatch.setattr(
        imports_pipeline,
        "load_home_host_vars",
        lambda _path: {
            "alpha": {"group_roles": {"valid.enable": True}},
            "zeta": {"group_roles": {"valid.enable": True}},
        },
    )

    def fail_second_dump(_data, path, _format, **_kwargs):
        path.write_text("version: staged\n", encoding="utf-8")
        if path.stem == "zeta":
            raise OSError("staging failed")

    monkeypatch.setattr(artifacts, "dump_yaml", fail_second_dump)

    with pytest.raises(OSError, match="staging failed"):
        imports_pipeline.build_home_merged_variables(
            tmp_path / "ansible",
            tmp_path / "autoconf",
            logger=Mock(),
        )

    assert previous_alpha.read_text(encoding="utf-8") == "version: previous\n"
    assert stale_file.read_text(encoding="utf-8") == "version: previous\n"
    assert not list((tmp_path / "autoconf").glob(".home_merged_vars.*"))


def test_inventory_loader_applies_configured_subnet_to_hosts(tmp_path):
    ansible_root = tmp_path / "ansible"
    inventory_dir = ansible_root / "inventory"
    inventory_dir.mkdir(parents=True)
    (ansible_root / "roles").mkdir()
    (inventory_dir / "group_vars").mkdir()
    (inventory_dir / "host_vars").mkdir()
    hosts_file = inventory_dir / "hosts.ini"
    hosts_file.write_text("[all]\nnode-01 ansible_host=10.20.30.4\n")

    inventory = AnsibleInventory.load_from_hosts_ini(hosts_file, subnet="10.20.30.")

    host = inventory.get_host_by_name("node-01")
    assert host is not None
    assert host.subnet == "10.20.30."
    assert host.ansible_host == "10.20.30.4"
    merged = inventory.export_merged_host_vars("node-01")
    assert (
        merged["group_luxnix"]["generic_settings.network.hosts.node_01.ip_vpn"]
        == '"10.20.30.4"'
    )


def test_system_import_fails_explicitly_when_inventory_is_missing(tmp_path):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )

    with pytest.raises(FileNotFoundError, match="Ansible inventory directory"):
        imports_pipeline.build_system_merged_variables(
            ansible_root=tmp_path / "ansible",
            autoconf_out=tmp_path / "autoconf",
            subnet="10.20.30.",
            system_group="active_clients",
            logger=Mock(),
        )
