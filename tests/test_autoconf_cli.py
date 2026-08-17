from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from lx_administration.autoconf.config import (
    AUTOCONF_OPTION_NAMES,
    DEFAULT_CONFIG_PATH,
    AutoconfConfig,
)
from lx_administration.autoconf.errors import (
    AutoconfPipelineError,
    AutoconfSourceError,
)
from lx_administration.autoconf.imports.ansible_facts import AnsibleFactFormatError
from tests.autoconf_test_support import isolated_source_script, write_config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_autoconf_cli_uses_canonical_config_from_any_working_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, REPO_ROOT / "scripts/autoconf-pipeline.py", "--check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"config: {DEFAULT_CONFIG_PATH}" in result.stdout
    assert all(f"\n{option}:" in result.stdout for option in AUTOCONF_OPTION_NAMES)
    assert "\ninventory_subnet:" not in result.stdout
    assert "\nhome_default_users:" not in result.stdout
    assert "autoconf configuration is valid" in result.stdout


def test_config_loader_cli_and_guide_share_canonical_option_names() -> None:
    config_text = (REPO_ROOT / "autoconf/config.yml").read_text(encoding="utf-8")
    raw_config = yaml.safe_load(config_text)
    config_option_names = tuple(
        f"{section}.{option}"
        for section in ("paths", "inventory", "home")
        for option in raw_config[section]
    )
    resolved_option_names = tuple(AutoconfConfig.load().resolved_options())
    guide = (REPO_ROOT / "docs/autoconf.md").read_text(encoding="utf-8")

    assert config_option_names == AUTOCONF_OPTION_NAMES
    assert resolved_option_names == AUTOCONF_OPTION_NAMES
    assert all(f"`{option}`" in guide for option in AUTOCONF_OPTION_NAMES)
    assert [guide.index(f"`{option}`") for option in AUTOCONF_OPTION_NAMES] == sorted(
        guide.index(f"`{option}`") for option in AUTOCONF_OPTION_NAMES
    )
    assert "devenv tasks run autoconf:check" in config_text
    assert "docs/autoconf.md" in config_text
    assert "sensitive, gitignored local fact snapshots" in config_text
    assert "config.yml itself is" in config_text


def test_autoconf_cli_prints_one_resolved_option_for_scripts(tmp_path) -> None:
    config_file = write_config(tmp_path)
    shutil.rmtree(tmp_path / "ansible/cmdb")

    result = subprocess.run(
        isolated_source_script(
            REPO_ROOT / "scripts/autoconf-pipeline.py",
            "--config",
            config_file,
            "--print-option",
            "paths.ansible_root",
        ),
        cwd="/tmp",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{tmp_path / 'ansible'}\n"


def test_vault_bootstrap_uses_central_autoconf_inventory_by_default(
    tmp_path,
) -> None:
    script = REPO_ROOT / "scripts/bootstrap-lx-vault.py"
    spec = importlib.util.spec_from_file_location("bootstrap_lx_vault", script)
    assert spec is not None and spec.loader is not None
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)

    config_file = write_config(tmp_path)
    args = bootstrap._parse_args(["--autoconf-config", str(config_file)])

    assert args.inventory is None
    assert (
        bootstrap._resolve_inventory_path(
            args.inventory,
            args.autoconf_config,
        )
        == tmp_path / "generated/inventory.yml"
    )


def test_vault_bootstrap_inventory_override_does_not_load_autoconf(
    monkeypatch,
    tmp_path,
) -> None:
    script = REPO_ROOT / "scripts/bootstrap-lx-vault.py"
    spec = importlib.util.spec_from_file_location("bootstrap_lx_vault", script)
    assert spec is not None and spec.loader is not None
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    inventory = tmp_path / "custom-inventory.yml"
    monkeypatch.setattr(
        bootstrap.AutoconfConfig,
        "load",
        Mock(side_effect=AssertionError("Autoconf config should not be loaded")),
    )

    assert (
        bootstrap._resolve_inventory_path(
            inventory,
            tmp_path / "missing-config.yml",
        )
        == inventory
    )


@pytest.mark.parametrize(
    "error_type",
    (AutoconfPipelineError, AnsibleFactFormatError, AutoconfSourceError),
)
def test_autoconf_cli_reports_pipeline_errors_without_traceback(
    monkeypatch, capsys, error_type
) -> None:
    script = REPO_ROOT / "scripts/autoconf-pipeline.py"
    spec = importlib.util.spec_from_file_location("autoconf_pipeline_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    class Config:
        def require_valid(self):
            return None

        def summary(self):
            return "config: test"

    def fail_pipeline(_config):
        raise error_type("invalid host configuration")

    monkeypatch.setattr(cli.AutoconfConfig, "load", lambda _path: Config())
    monkeypatch.setattr(cli, "run_pipeline", fail_pipeline)

    assert cli.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == "config: test\n"
    assert captured.err == ("autoconf generation error: invalid host configuration\n")
    assert "Traceback" not in captured.err


def test_autoconf_cli_validates_once_before_generation(monkeypatch, capsys) -> None:
    script = REPO_ROOT / "scripts/autoconf-pipeline.py"
    spec = importlib.util.spec_from_file_location("autoconf_pipeline_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    config = Mock()
    config.summary.return_value = "config: test"
    generated = []
    monkeypatch.setattr(cli.AutoconfConfig, "load", lambda _path: config)
    monkeypatch.setattr(cli, "run_pipeline", generated.append)

    assert cli.main([]) == 0
    config.require_valid.assert_called_once_with()
    assert generated == [config]
    assert capsys.readouterr().out == "config: test\n"


def test_autoconf_cli_uses_explicit_external_target_for_isolated_render(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    script = REPO_ROOT / "scripts/autoconf-pipeline.py"
    spec = importlib.util.spec_from_file_location("autoconf_pipeline_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    config = Mock()
    config.summary.return_value = "config: test"
    rendered = []
    monkeypatch.setattr(cli.AutoconfConfig, "load", lambda _path: config)
    monkeypatch.setattr(cli, "run_pipeline", lambda _config: pytest.fail("pipeline"))
    monkeypatch.setattr(
        cli,
        "run_isolated_nix_render",
        lambda render_config, destination: rendered.append(
            (render_config, destination)
        ),
    )
    output = tmp_path / "isolated-render"

    assert cli.main(["--nix-output", str(output)]) == 0

    config.require_valid.assert_called_once_with()
    assert rendered == [(config, output.resolve())]
    assert capsys.readouterr().out == (
        f"config: test\nisolated Nix render output: {output.resolve()}\n"
    )


def test_autoconf_cli_rejects_isolated_target_inside_repository(
    monkeypatch,
    capsys,
) -> None:
    script = REPO_ROOT / "scripts/autoconf-pipeline.py"
    spec = importlib.util.spec_from_file_location("autoconf_pipeline_cli", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    config = Mock()
    config.summary.return_value = "config: test"
    monkeypatch.setattr(cli.AutoconfConfig, "load", lambda _path: config)
    monkeypatch.setattr(
        cli,
        "run_isolated_nix_render",
        lambda *_args: pytest.fail("isolated render"),
    )

    assert cli.main(["--nix-output", str(REPO_ROOT / "render-preview")]) == 1

    captured = capsys.readouterr()
    assert captured.out == "config: test\n"
    assert "outside the repository" in captured.err
