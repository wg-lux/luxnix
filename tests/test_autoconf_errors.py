from __future__ import annotations

import pytest
import yaml

from lx_administration.autoconf.config import AutoconfConfigError
from lx_administration.autoconf.errors import (
    AnsibleFactFormatError as ErrorModuleFactError,
)
from lx_administration.autoconf.errors import (
    AutoconfConfigError as ErrorModuleConfigError,
)
from lx_administration.autoconf.errors import (
    AutoconfPipelineError,
    AutoconfSourceError,
    AutoconfSourceNotFoundError,
    AutoconfYamlError,
)
from lx_administration.autoconf.imports.ansible_facts import AnsibleFactFormatError
from lx_administration.autoconf.imports.sources import (
    load_group_vars,
    load_home_host_vars,
)


def test_autoconf_config_error_has_one_public_identity() -> None:
    from lx_administration.autoconf import (
        AutoconfConfigError as PublicConfigError,
    )

    assert AutoconfConfigError is ErrorModuleConfigError
    assert PublicConfigError is ErrorModuleConfigError


def test_ansible_fact_error_has_one_public_identity() -> None:
    from lx_administration.autoconf import (
        AnsibleFactFormatError as PublicFactError,
    )
    from lx_administration.autoconf.imports import (
        AnsibleFactFormatError as ImportFacadeFactError,
    )

    assert AnsibleFactFormatError is ErrorModuleFactError
    assert PublicFactError is ErrorModuleFactError
    assert ImportFacadeFactError is ErrorModuleFactError
    assert issubclass(ErrorModuleFactError, AutoconfPipelineError)
    assert issubclass(ErrorModuleFactError, ValueError)


def test_autoconf_source_error_is_cli_safe_and_value_error_compatible() -> None:
    from lx_administration.autoconf import (
        AutoconfSourceError as PublicSourceError,
    )

    assert PublicSourceError is AutoconfSourceError
    assert issubclass(AutoconfSourceError, AutoconfPipelineError)
    assert issubclass(AutoconfSourceError, ValueError)
    assert issubclass(AutoconfSourceNotFoundError, AutoconfSourceError)
    assert issubclass(AutoconfSourceNotFoundError, FileNotFoundError)
    assert issubclass(AutoconfYamlError, AutoconfSourceError)
    assert issubclass(AutoconfYamlError, yaml.YAMLError)


def test_autoconf_source_error_does_not_expose_invalid_yaml(tmp_path) -> None:
    group_vars = tmp_path / "group_vars"
    group_vars.mkdir()
    invalid_file = group_vars / "all.yml"
    invalid_file.write_text('secret: "TOP_SECRET', encoding="utf-8")

    with pytest.raises(AutoconfSourceError) as error:
        load_group_vars(group_vars)

    assert str(error.value) == f"Invalid YAML in {invalid_file}"
    assert "TOP_SECRET" not in str(error.value)


def test_home_loader_reports_missing_manifest_without_traceback(tmp_path) -> None:
    with pytest.raises(
        AutoconfSourceNotFoundError,
        match="Autoconf YAML source not found",
    ) as error:
        load_home_host_vars(tmp_path)

    assert str(tmp_path / "home-hosts.yml") in str(error.value)
