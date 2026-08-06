import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def _run_isolated_import(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", source],
        cwd=REPO_ROOT,
        env=os.environ | {"PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_autoconf_import_does_not_load_password_or_vault_subsystems() -> None:
    result = _run_isolated_import(
        """
import sys
import lx_administration.autoconf.config
import lx_administration.autoconf.imports
import lx_administration.autoconf.nix
import lx_administration.models.ansible.facts

assert "lx_administration.autoconf.imports.main" not in sys.modules
assert "lx_administration.autoconf.imports.ansible_facts" not in sys.modules
assert "lx_administration.autoconf.imports.ansible_inventory" not in sys.modules
assert "lx_administration.autoconf.nix.main" not in sys.modules
assert "lx_administration.password.generator" not in sys.modules
assert "lx_administration.models.ansible.inventory" not in sys.modules
assert "lx_administration.models.vault.manager" not in sys.modules
assert "lx_administration.yaml.checkfile" not in sys.modules
assert "lx_administration.yaml.dump" not in sys.modules
assert "lx_administration.storage.manager" not in sys.modules
assert "lx_administration.storage.mounting" not in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


def test_autoconf_package_keeps_pipeline_code_lazy() -> None:
    result = _run_isolated_import(
        """
import sys
import lx_administration.autoconf

assert "lx_administration.autoconf.config" not in sys.modules
assert "lx_administration.autoconf.main" not in sys.modules
assert "AnsibleInventoryLayout" in dir(lx_administration.autoconf)
assert "AutoconfConfig" in dir(lx_administration.autoconf)
assert "AutoconfOutputLayout" in dir(lx_administration.autoconf)
assert "AutoconfSourceLayout" in dir(lx_administration.autoconf)
assert "NixOutputLayout" in dir(lx_administration.autoconf)
assert "NixTemplateLayout" in dir(lx_administration.autoconf)
assert "run_from_config" in dir(lx_administration.autoconf)
from lx_administration.autoconf import (
    AnsibleInventoryLayout,
    AutoconfConfig,
    AutoconfOutputLayout,
    AutoconfSourceLayout,
    NixOutputLayout,
    NixTemplateLayout,
)
from lx_administration.autoconf.layout import (
    AnsibleInventoryLayout as DirectAnsibleInventoryLayout,
    AutoconfOutputLayout as DirectAutoconfOutputLayout,
    AutoconfSourceLayout as DirectAutoconfSourceLayout,
    NixOutputLayout as DirectNixOutputLayout,
    NixTemplateLayout as DirectNixTemplateLayout,
)
assert AutoconfConfig.__name__ == "AutoconfConfig"
assert AnsibleInventoryLayout is DirectAnsibleInventoryLayout
assert AutoconfOutputLayout is DirectAutoconfOutputLayout
assert AutoconfSourceLayout is DirectAutoconfSourceLayout
assert NixOutputLayout is DirectNixOutputLayout
assert NixTemplateLayout is DirectNixTemplateLayout
assert "lx_administration.autoconf.config" in sys.modules
assert "lx_administration.autoconf.main" not in sys.modules
from lx_administration.autoconf import run_from_config
from lx_administration.autoconf.main import run_from_config as direct_run
assert run_from_config is direct_run
"""
    )

    assert result.returncode == 0, result.stderr


def test_root_package_keeps_its_lazy_public_api() -> None:
    result = _run_isolated_import(
        """
import sys
import lx_administration

assert "lx_administration.password.generator" not in sys.modules
assert "PasswordGenerator" in dir(lx_administration)
assert not hasattr(lx_administration, "MissingExport")
from lx_administration import PasswordGenerator
from lx_administration.password import PasswordGenerator as DirectPasswordGenerator
assert PasswordGenerator is DirectPasswordGenerator
assert lx_administration.PasswordGenerator is PasswordGenerator
"""
    )

    assert result.returncode == 0, result.stderr


def test_password_package_keeps_heavy_dependencies_lazy() -> None:
    result = _run_isolated_import(
        """
import sys
import lx_administration.password

assert "lx_administration.password.generator" not in sys.modules
assert "faker" not in sys.modules
assert "passlib" not in sys.modules
assert "PasswordGenerator" in dir(lx_administration.password)
from lx_administration.password import PasswordGenerator
assert PasswordGenerator.__name__ == "PasswordGenerator"
assert "lx_administration.password.generator" in sys.modules
"""
    )

    assert result.returncode == 0, result.stderr


def test_models_package_keeps_its_lazy_public_api() -> None:
    result = _run_isolated_import(
        """
import sys
import lx_administration.models

assert "lx_administration.models.vault.manager" not in sys.modules
from lx_administration.models import Vault
from lx_administration.models.vault.manager import Vault as DirectVault
assert Vault is DirectVault
"""
    )

    assert result.returncode == 0, result.stderr


def test_vault_models_package_keeps_its_public_api_lazy() -> None:
    result = _run_isolated_import(
        """
import sys
import lx_administration.models.vault

assert "lx_administration.models.vault.admin_passwords" not in sys.modules
assert "lx_administration.models.vault.manager" not in sys.modules
assert "lx_administration.models.vault.secret" not in sys.modules
assert "Vault" in dir(lx_administration.models.vault)
assert "Secret" in dir(lx_administration.models.vault)
assert "load_admin_passwords" in dir(lx_administration.models.vault)
assert "import_admin_passwords" in dir(lx_administration.models.vault)
from lx_administration.models.vault import (
    import_admin_passwords,
    load_admin_passwords,
)
from lx_administration.models.vault.admin_passwords import (
    import_admin_passwords as direct_import_admin_passwords,
    load_admin_passwords as direct_load_admin_passwords,
)
assert import_admin_passwords is direct_import_admin_passwords
assert load_admin_passwords is direct_load_admin_passwords
from lx_administration.models.vault import Secret, Vault
from lx_administration.models.vault.manager import Vault as DirectVault
from lx_administration.models.vault.secret import Secret as DirectSecret
assert Vault is DirectVault
assert Secret is DirectSecret
"""
    )

    assert result.returncode == 0, result.stderr


def test_autoconf_facade_exposes_real_functions_and_signatures() -> None:
    result = _run_isolated_import(
        """
import inspect
from lx_administration.autoconf.imports import import_source_data, load_all_host_facts
from lx_administration.autoconf.imports.ansible_facts import (
    load_all_host_facts as direct_load_all_host_facts,
)
from lx_administration.autoconf.imports.main import (
    import_source_data as direct_import_source_data,
)
from lx_administration.autoconf.nix import render_configurations
from lx_administration.autoconf.nix.main import (
    render_configurations as direct_render_configurations,
)

assert load_all_host_facts is direct_load_all_host_facts
assert import_source_data is direct_import_source_data
assert render_configurations is direct_render_configurations
assert tuple(inspect.signature(load_all_host_facts).parameters) == ("facts_dir",)
assert "subnet" in inspect.signature(import_source_data).parameters
assert tuple(inspect.signature(render_configurations).parameters) == (
    "config",
    "logger",
)
"""
    )

    assert result.returncode == 0, result.stderr


def test_every_declared_lazy_export_resolves() -> None:
    result = _run_isolated_import(
        """
import lx_administration
import lx_administration.autoconf
import lx_administration.autoconf.imports
import lx_administration.autoconf.nix
import lx_administration.models
import lx_administration.models.ansible
import lx_administration.models.vault
import lx_administration.password
import lx_administration.storage
import lx_administration.yaml

packages = (
    lx_administration,
    lx_administration.autoconf,
    lx_administration.autoconf.imports,
    lx_administration.autoconf.nix,
    lx_administration.models,
    lx_administration.models.ansible,
    lx_administration.models.vault,
    lx_administration.password,
    lx_administration.storage,
    lx_administration.yaml,
)
for package in packages:
    for name in package.__all__:
        assert getattr(package, name) is not None, f"{package.__name__}.{name}"
"""
    )

    assert result.returncode == 0, result.stderr
