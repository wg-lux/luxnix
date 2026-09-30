import sys
from pathlib import Path

import yaml


def isolated_source_script(script: Path, *arguments: object) -> list[str]:
    """Run a source-tree script without loading editable-install .pth files."""
    site_packages = Path(yaml.__file__).parents[1]
    bootstrap = """
import runpy
import sys

site_packages = sys.argv.pop(1)
script = sys.argv.pop(1)
sys.path.append(site_packages)
sys.argv[0] = script
runpy.run_path(script, run_name="__main__")
"""
    return [
        sys.executable,
        "-S",
        "-c",
        bootstrap,
        str(site_packages),
        str(script),
        *(str(argument) for argument in arguments),
    ]


def write_config(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "ansible/inventory").mkdir(parents=True)
    (tmp_path / "ansible/inventory/hosts.ini").write_text("[all]\n")
    (tmp_path / "ansible/inventory/home-hosts.yml").write_text(
        "schema_version: 1\nhosts: {}\n",
        encoding="utf-8",
    )
    (tmp_path / "ansible/inventory/host_vars/home").mkdir(parents=True)
    (tmp_path / "ansible/cmdb").mkdir()
    (tmp_path / "templates/systems").mkdir(parents=True)
    (tmp_path / "templates/homes").mkdir()
    (tmp_path / "output").mkdir()
    config_file = tmp_path / "config.yml"
    config_file.write_text(
        """schema_version: 1
paths:
  ansible_root: ansible
  output: generated
  nix_output: output
  nix_templates: templates
  report_output: report/index.html
inventory:
  subnet: 10.20.30.
  system_group: active_clients
home:
  default_users:
    - operator
  state_version: "23.11"
"""
        + extra
    )
    return config_file
