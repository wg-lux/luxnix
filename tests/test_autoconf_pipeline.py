from __future__ import annotations

import importlib
import inspect
from unittest.mock import Mock

from lx_administration.autoconf.config import AutoconfConfig
from lx_administration.models.ansible.inventory import AnsibleInventory
from tests.autoconf_test_support import write_config


def test_pipeline_uses_central_config(monkeypatch, tmp_path):
    pipeline = importlib.import_module("lx_administration.autoconf.main")
    config = AutoconfConfig.load(write_config(tmp_path))
    received = {}

    def fake_source_import(ansible_root, autoconf_out, subnet, system_group, logger):
        received["subnet"] = subnet
        received["system_group"] = system_group
        return None

    def fake_render_configurations(render_config, *, logger):
        received["render_config"] = render_config
        received["render_logger"] = logger

    def fake_get_logger(name, *, log_dir, reset):
        received["logger_name"] = name
        received["log_dir"] = log_dir
        received["reset"] = reset
        return Mock()

    monkeypatch.setattr(pipeline, "import_source_data", fake_source_import)
    monkeypatch.setattr(
        pipeline,
        "build_home_merged_variables",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pipeline,
        "render_configurations",
        fake_render_configurations,
    )
    monkeypatch.setattr(pipeline, "get_logger", fake_get_logger)
    monkeypatch.setattr(pipeline, "shutdown_logging", lambda: None)

    pipeline.run_pipeline(config)

    assert received["subnet"] == "10.20.30."
    assert received["system_group"] == "active_clients"
    assert received["render_config"] is config
    assert received["render_logger"] is not None
    assert received["logger_name"] == "autoconf_pipeline"
    assert received["log_dir"] == config.log_dir
    assert received["reset"] is True


def test_source_import_uses_canonical_default_logger(monkeypatch, tmp_path):
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    received = {}
    logger = Mock()
    inventory = Mock()

    def fake_get_logger(name, *, log_dir, reset):
        received.update(name=name, log_dir=log_dir, reset=reset)
        return logger

    monkeypatch.setattr(imports_pipeline, "get_logger", fake_get_logger)
    monkeypatch.setattr(
        imports_pipeline,
        "build_system_merged_variables",
        lambda *args, **kwargs: inventory,
    )

    result = imports_pipeline.import_source_data(
        ansible_root=tmp_path / "ansible",
        autoconf_out=tmp_path / "autoconf",
        subnet="10.20.30.",
        system_group="active_clients",
    )

    assert result is inventory
    assert received == {
        "name": "autoconf_source_import",
        "log_dir": tmp_path / "autoconf/logs",
        "reset": True,
    }


def test_run_from_config_dispatches_central_config_unchanged(monkeypatch, tmp_path):
    pipeline = importlib.import_module("lx_administration.autoconf.main")
    config = AutoconfConfig.load(write_config(tmp_path))
    received = []

    monkeypatch.setattr(
        pipeline,
        "run_pipeline",
        received.append,
    )

    pipeline.run_from_config(config)

    assert received == [config]


def test_historical_pipeline_aliases_are_removed():
    pipeline = importlib.import_module("lx_administration.autoconf.main")
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    home_renderer = importlib.import_module("lx_administration.autoconf.nix.home")

    assert not hasattr(pipeline, "pipe")
    assert not hasattr(pipeline, "pipe_from_config")
    assert not hasattr(imports_pipeline, "pipe")
    assert not hasattr(imports_pipeline, "home_etl")
    assert not hasattr(imports_pipeline, "ansible_etl")
    assert not hasattr(nix_pipeline, "pipe")
    assert not hasattr(nix_pipeline, "generate_default_nix")
    assert not hasattr(home_renderer, "home_pipe")


def test_pipeline_has_no_hidden_path_or_subnet_defaults() -> None:
    pipeline = importlib.import_module("lx_administration.autoconf.main")
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    inventory_loader = importlib.import_module(
        "lx_administration.autoconf.imports.ansible_inventory"
    )
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")

    required_parameters = (
        (pipeline.run_pipeline, "config"),
        (imports_pipeline.import_source_data, "subnet"),
        (imports_pipeline.import_source_data, "system_group"),
        (inventory_loader.load_inventory_hostfile, "subnet"),
        (AnsibleInventory.load_from_hosts_ini, "subnet"),
        (AnsibleInventory.save_to_file, "inventory_file"),
        (nix_pipeline.render_configurations, "config"),
        (nix_pipeline.render_default_nix, "config"),
    )
    for function, parameter in required_parameters:
        assert (
            inspect.signature(function).parameters[parameter].default
            is inspect.Parameter.empty
        ), f"{function.__module__}.{function.__name__}.{parameter} must be explicit"


def test_canonical_pipeline_stages_have_complete_type_signatures() -> None:
    pipeline = importlib.import_module("lx_administration.autoconf.main")
    imports_pipeline = importlib.import_module(
        "lx_administration.autoconf.imports.main"
    )
    inventory_loader = importlib.import_module(
        "lx_administration.autoconf.imports.ansible_inventory"
    )
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    home_renderer = importlib.import_module("lx_administration.autoconf.nix.home")

    stages = (
        pipeline.run_pipeline,
        pipeline.run_from_config,
        imports_pipeline.import_source_data,
        imports_pipeline.build_system_merged_variables,
        imports_pipeline.build_home_merged_variables,
        inventory_loader.load_inventory_hostfile,
        nix_pipeline.render_configurations,
        nix_pipeline.render_default_nix,
        home_renderer.render_home_outputs,
    )
    for stage in stages:
        signature = inspect.signature(stage)
        assert signature.return_annotation is not inspect.Signature.empty
        assert all(
            parameter.annotation is not inspect.Parameter.empty
            for parameter in signature.parameters.values()
        ), f"{stage.__module__}.{stage.__name__} has an untyped parameter"
