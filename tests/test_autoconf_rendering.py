import importlib
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from jinja2 import UndefinedError

from lx_administration.autoconf.config import AutoconfConfig
from lx_administration.autoconf.errors import AutoconfPipelineError
from lx_administration.autoconf.nix.template_renderer import render_nix_template

REPO_ROOT = Path(__file__).resolve().parents[1]


def _render_config(tmp_path: Path) -> AutoconfConfig:
    """Build renderer options without creating unrelated source directories."""
    return AutoconfConfig(
        source=tmp_path / "config.yml",
        ansible_root=tmp_path / "ansible",
        output=tmp_path / "autoconf",
        nix_output=tmp_path / "output",
        nix_templates=tmp_path / "templates",
        report_output=tmp_path / "report/index.html",
        inventory_subnet="10.20.30.",
        inventory_system_group="active_clients",
        home_default_users=("operator",),
        home_state_version="23.11",
    )


def test_missing_system_template_fails_explicitly(tmp_path: Path) -> None:
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    config = _render_config(tmp_path)

    with pytest.raises(AutoconfPipelineError, match="Nix system template directory"):
        nix_pipeline.get_template_dir_for_host(
            config.template_layout,
            "x86_64-linux",
            "missing",
        )


def test_missing_home_template_fails_explicitly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home_renderer = importlib.import_module("lx_administration.autoconf.nix.home")
    config = _render_config(tmp_path)
    home_vars_dir = config.output_layout.home_vars_dir
    home_vars_dir.mkdir(parents=True)
    (home_vars_dir / "node-01.yml").touch()

    class FakeMergedVars:
        system_users = ("operator",)

        def get_host_platform(self) -> str:
            return "x86_64-linux"

    monkeypatch.setattr(
        home_renderer.MergedHostVars,
        "load_home_from_file",
        lambda _path: FakeMergedVars(),
    )

    with pytest.raises(
        AutoconfPipelineError,
        match="Home Manager template directory not found",
    ):
        home_renderer.render_home_outputs(
            config=config,
            logger=Mock(),
        )


def test_system_renderer_adds_hostname_to_template_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    config = _render_config(tmp_path)
    (tmp_path / "templates/systems/x86_64-linux/main").mkdir(parents=True)
    received: dict[str, Any] = {}

    class FakeMergedVars:
        template_name = "main"

        def export_host_config(self, logger: object = None) -> dict[str, object]:
            return {"role_configs": {}}

    monkeypatch.setattr(
        nix_pipeline,
        "render_nix_template",
        lambda _directory, _template, context: received.update(context) or "nix",
    )

    output, rendered = nix_pipeline.render_default_nix(
        hostname="node-01",
        merged_vars=FakeMergedVars(),
        host_platform="x86_64-linux",
        config=config,
    )

    assert received["hostname"] == "node-01"
    assert output == tmp_path / "output/systems/x86_64-linux/node-01/default.nix"
    assert rendered == "nix"


def test_home_renderer_uses_configured_defaults_without_logging_rendered_data() -> None:
    renderer = (REPO_ROOT / "lx_administration/autoconf/nix/home.py").read_text()
    template = (
        REPO_ROOT / "conf/nix-templates/homes/x86_64-linux/default.nix.j2"
    ).read_text()

    assert "merged_vars.system_users or config.home_default_users" in renderer
    assert "state_version=config.home_state_version" in renderer
    assert "home.stateVersion = {{ stateVersion | nix_string }};" in template
    assert 'home.stateVersion = "23.11";' not in template
    assert '["admin"]' not in renderer
    assert "Rendered:" not in renderer
    assert "#print" not in renderer


def test_system_renderer_does_not_use_legacy_export_side_effects() -> None:
    system_renderer = (REPO_ROOT / "lx_administration/autoconf/nix/main.py").read_text()

    assert "export = True" not in system_renderer
    assert "export = False" not in system_renderer
    assert "os.makedirs" not in system_renderer


def test_nix_writer_has_one_explicit_responsibility() -> None:
    writer = (REPO_ROOT / "lx_administration/autoconf/nix/utils.py").read_text()

    assert "def write_nix_file(" in writer
    assert "def load_config(" not in writer
    assert "import yaml" not in writer
    assert "get_logger(" not in writer


def test_shared_nix_renderer_rejects_missing_template_variables(
    tmp_path: Path,
) -> None:
    template = tmp_path / "default.nix.j2"
    template.write_text("value = {{ missing_value }};", encoding="utf-8")

    with pytest.raises(UndefinedError, match="missing_value"):
        render_nix_template(tmp_path, template.name, {})


def test_system_renderer_processes_hosts_in_filename_order(monkeypatch, tmp_path):
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    config = _render_config(tmp_path)
    merged_vars_dir = tmp_path / "autoconf/merged_vars"
    merged_vars_dir.mkdir(parents=True)
    (tmp_path / "templates/systems/x86_64-linux/main").mkdir(parents=True)
    for hostname in ("zeta", "alpha"):
        (merged_vars_dir / f"{hostname}.yml").touch()

    platform_lookups = []

    class FakeMergedVars:
        def __init__(self, hostname):
            self.hostname = hostname
            self.template_name = "main"

        def get_host_platform(self, logger=None):
            platform_lookups.append(self.hostname)
            return "x86_64-linux"

    monkeypatch.setattr(
        nix_pipeline.MergedHostVars,
        "load_from_file",
        lambda path, logger=None: FakeMergedVars(Path(path).stem),
    )
    rendered = []
    monkeypatch.setattr(
        nix_pipeline,
        "render_default_nix",
        lambda hostname, *args, **kwargs: (
            tmp_path / f"{hostname}.nix",
            hostname,
        ),
    )
    monkeypatch.setattr(
        nix_pipeline,
        "write_nix_outputs",
        lambda outputs, *args, **kwargs: rendered.extend(
            content for _path, content in outputs
        ),
    )
    monkeypatch.setattr(nix_pipeline, "render_home_outputs", lambda *args, **kwargs: [])

    nix_pipeline.render_configurations(
        config=config,
    )

    assert rendered == ["alpha", "zeta"]
    assert platform_lookups == ["alpha", "zeta"]


def test_home_renderer_processes_hosts_in_filename_order(monkeypatch, tmp_path):
    home_renderer = importlib.import_module("lx_administration.autoconf.nix.home")
    config = _render_config(tmp_path)
    merged_vars_dir = config.output_layout.home_vars_dir
    merged_vars_dir.mkdir(parents=True)
    (tmp_path / "templates/homes/x86_64-linux").mkdir(parents=True)
    for hostname in ("zeta", "alpha"):
        (merged_vars_dir / f"{hostname}.yml").touch()

    prepared = []

    class FakeMergedVars:
        system_users = None

        def get_host_platform(self):
            return "x86_64-linux"

        def prepare_home_config(self, username, state_version):
            prepared.append((username, state_version))
            return {"username": username}

    monkeypatch.setattr(
        home_renderer.MergedHostVars,
        "load_home_from_file",
        lambda _path: FakeMergedVars(),
    )
    monkeypatch.setattr(home_renderer, "render_nix_template", lambda *args: "nix")
    outputs = home_renderer.render_home_outputs(
        config=config,
        logger=Mock(),
    )

    assert [path.parent.name for path, _content in outputs] == [
        "operator@alpha",
        "operator@zeta",
    ]
    assert prepared == [("operator", "23.11"), ("operator", "23.11")]


def test_system_renderer_validates_all_hosts_before_generating(monkeypatch, tmp_path):
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    config = _render_config(tmp_path)
    merged_vars_dir = tmp_path / "autoconf/merged_vars"
    merged_vars_dir.mkdir(parents=True)
    for hostname in ("alpha", "zeta"):
        (merged_vars_dir / f"{hostname}.yml").touch()
    (tmp_path / "templates/systems/x86_64-linux/main").mkdir(parents=True)

    class FakeMergedVars:
        template_name = "main"

        def __init__(self, hostname):
            self.hostname = hostname

        def get_host_platform(self, logger=None):
            if self.hostname == "zeta":
                raise ValueError("sensitive invalid value")
            return "x86_64-linux"

    monkeypatch.setattr(
        nix_pipeline.MergedHostVars,
        "load_from_file",
        lambda path, logger=None: FakeMergedVars(Path(path).stem),
    )
    generated = []
    monkeypatch.setattr(
        nix_pipeline,
        "render_default_nix",
        lambda *args, **kwargs: generated.append(args[0]),
    )

    with pytest.raises(AutoconfPipelineError, match="zeta") as error:
        nix_pipeline.render_configurations(
            config=config,
        )

    assert generated == []
    assert "sensitive invalid value" not in str(error.value)


def test_system_renderer_renders_all_hosts_before_writing(monkeypatch, tmp_path):
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    config = _render_config(tmp_path)
    merged_vars_dir = tmp_path / "autoconf/merged_vars"
    merged_vars_dir.mkdir(parents=True)
    (tmp_path / "templates/systems/x86_64-linux/main").mkdir(parents=True)
    for hostname in ("alpha", "zeta"):
        (merged_vars_dir / f"{hostname}.yml").touch()

    class FakeMergedVars:
        template_name = "main"

        def __init__(self, hostname):
            self.hostname = hostname

        def get_host_platform(self, logger=None):
            return "x86_64-linux"

        def export_host_config(self, logger=None):
            return {}

    monkeypatch.setattr(
        nix_pipeline.MergedHostVars,
        "load_from_file",
        lambda path, logger=None: FakeMergedVars(Path(path).stem),
    )

    def fake_render(_template_path, _template_name, config):
        if config["hostname"] == "zeta":
            raise TypeError("sensitive invalid value")
        return "nix"

    monkeypatch.setattr(nix_pipeline, "render_nix_template", fake_render)
    written = []
    monkeypatch.setattr(
        nix_pipeline,
        "write_nix_outputs",
        lambda *args, **kwargs: written.append(args),
    )

    with pytest.raises(AutoconfPipelineError, match="zeta") as error:
        nix_pipeline.render_configurations(
            config=config,
        )

    assert written == []
    assert not (tmp_path / "output").exists()
    assert "sensitive invalid value" not in str(error.value)


def test_nix_pipeline_renders_homes_before_writing_systems(monkeypatch, tmp_path):
    nix_pipeline = importlib.import_module("lx_administration.autoconf.nix.main")
    config = _render_config(tmp_path)
    merged_vars_dir = tmp_path / "autoconf/merged_vars"
    merged_vars_dir.mkdir(parents=True)
    (merged_vars_dir / "alpha.yml").touch()
    (tmp_path / "templates/systems/x86_64-linux/main").mkdir(parents=True)

    class FakeMergedVars:
        template_name = "main"

        def get_host_platform(self, logger=None):
            return "x86_64-linux"

    monkeypatch.setattr(
        nix_pipeline.MergedHostVars,
        "load_from_file",
        lambda *args, **kwargs: FakeMergedVars(),
    )
    monkeypatch.setattr(
        nix_pipeline,
        "render_default_nix",
        lambda *args, **kwargs: (tmp_path / "output/system.nix", "system"),
    )

    def fail_home_render(*args, **kwargs):
        raise AutoconfPipelineError("invalid Home Manager configuration")

    monkeypatch.setattr(nix_pipeline, "render_home_outputs", fail_home_render)
    published = []
    monkeypatch.setattr(
        nix_pipeline,
        "write_nix_outputs",
        lambda *args, **kwargs: published.append(args),
    )

    with pytest.raises(AutoconfPipelineError, match="Home Manager"):
        nix_pipeline.render_configurations(
            config=config,
        )

    assert published == []
    assert not (tmp_path / "output").exists()


def test_home_renderer_renders_all_hosts_before_writing(monkeypatch, tmp_path):
    home_renderer = importlib.import_module("lx_administration.autoconf.nix.home")
    config = _render_config(tmp_path)
    merged_vars_dir = config.output_layout.home_vars_dir
    merged_vars_dir.mkdir(parents=True)
    (tmp_path / "templates/homes/x86_64-linux").mkdir(parents=True)
    for hostname in ("alpha", "zeta"):
        (merged_vars_dir / f"{hostname}.yml").touch()

    class FakeMergedVars:
        system_users = ["operator"]

        def __init__(self, hostname):
            self.hostname = hostname

        def get_host_platform(self):
            return "x86_64-linux"

        def prepare_home_config(self, username, state_version):
            return {"hostname": self.hostname}

    monkeypatch.setattr(
        home_renderer.MergedHostVars,
        "load_home_from_file",
        lambda path: FakeMergedVars(Path(path).stem),
    )

    def fake_render(_template_path, _template_name, config):
        if config["hostname"] == "zeta":
            raise TypeError("sensitive invalid value")
        return "nix"

    monkeypatch.setattr(home_renderer, "render_nix_template", fake_render)
    with pytest.raises(AutoconfPipelineError, match="operator@zeta") as error:
        home_renderer.render_home_outputs(
            config=config,
            logger=Mock(),
        )

    assert not (tmp_path / "output").exists()
    assert "sensitive invalid value" not in str(error.value)
