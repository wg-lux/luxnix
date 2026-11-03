from __future__ import annotations

import importlib
import inspect
from unittest.mock import Mock

import pytest

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
    staged = received["render_config"]
    assert staged.ansible_root == config.ansible_root
    assert staged.nix_templates == config.nix_templates
    assert staged.output != config.output
    assert staged.nix_output != config.nix_output
    assert staged.inventory_subnet == config.inventory_subnet
    assert staged.home_state_version == config.home_state_version
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


def test_failed_render_preserves_previous_intermediates_and_nix(monkeypatch, tmp_path):

    pipeline = importlib.import_module("lx_administration.autoconf.main")
    config = AutoconfConfig.load(write_config(tmp_path))
    config.output.mkdir(parents=True)
    old_inventory = config.output / "inventory.yml"
    old_inventory.write_text("old inventory")
    old_nix = config.nix_output / "systems/node/default.nix"
    old_nix.parent.mkdir(parents=True)
    old_nix.write_text("old nix")

    def imported(_source, output, **kwargs):
        output.mkdir(parents=True)
        (output / "inventory.yml").write_text("new inventory")

    def failed_render(staged, **kwargs):
        assert old_inventory.read_text() == "old inventory"
        assert old_nix.read_text() == "old nix"
        raise RuntimeError("new home template is invalid")

    monkeypatch.setattr(pipeline, "import_source_data", imported)
    monkeypatch.setattr(pipeline, "build_home_merged_variables", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "render_configurations", failed_render)
    with pytest.raises(RuntimeError, match="home template"):
        pipeline.run_pipeline(config)
    assert old_inventory.read_text() == "old inventory"
    assert old_nix.read_text() == "old nix"


@pytest.mark.parametrize('fail_publication', [False, True])
def test_generation_commits_intermediates_and_nix_together(monkeypatch, tmp_path, fail_publication):
    from lx_administration.autoconf import publication
    pipeline = importlib.import_module('lx_administration.autoconf.main')
    config = AutoconfConfig.load(write_config(tmp_path))
    config.output.mkdir(parents=True)
    inventory = config.output / 'inventory.yml'
    inventory.write_text('old inventory')
    nix = config.nix_output / 'systems/node/default.nix'
    nix.parent.mkdir(parents=True)
    nix.write_text('old nix')
    def imported(_source, output, **kwargs):
        output.mkdir(parents=True)
        (output / 'inventory.yml').write_text('new inventory')
    def rendered(staged, **kwargs):
        target = staged.nix_output / 'systems/node/default.nix'
        target.parent.mkdir(parents=True)
        target.write_text('new nix')
    monkeypatch.setattr(pipeline, 'import_source_data', imported)
    monkeypatch.setattr(pipeline, 'build_home_merged_variables', lambda *a, **k: None)
    monkeypatch.setattr(pipeline, 'render_configurations', rendered)
    original = publication._replace
    def replace(source, target, mode):
        if fail_publication and target == nix and source.name.endswith('.new'):
            raise OSError('final Nix publication failed')
        original(source, target, mode)
    monkeypatch.setattr(publication, '_replace', replace)
    if fail_publication:
        with pytest.raises(OSError, match='final Nix publication failed'):
            pipeline.run_pipeline(config)
        assert inventory.read_text() == 'old inventory'
        assert nix.read_text() == 'old nix'
    else:
        pipeline.run_pipeline(config)
        assert inventory.read_text() == 'new inventory'
        assert nix.read_text() == 'new nix'
        assert inventory.stat().st_mode & 0o777 == 0o600
        assert nix.stat().st_mode & 0o777 == 0o644
    assert not (config.output / '.autoconf-publication').exists()
