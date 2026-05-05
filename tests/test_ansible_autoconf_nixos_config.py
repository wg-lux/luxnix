import shutil
import subprocess

import pytest

from lx_administration.autoconf.nix.template_renderer import render_nix_template
from lx_administration.autoconf.nix.utils import write_nix_file
from lx_administration.models import MergedHostVars


def test_merged_host_vars_exports_top_level_nixos_and_imports():
    merged = MergedHostVars(
        group_roles={"custom_packages.enable": True},
        group_nixos={
            "networking.firewall.allowedTCPPorts": [22],
            "boot.kernel.sysctl.\"net.core.rmem_max\"": 8388608,
        },
        role_nixos={
            "networking.firewall.allowedTCPPorts": [22, 443],
            "programs.zsh.enable": True,
        },
        host_nixos={
            "nix.settings.max_jobs": '"auto"',
            "networking.hostName": '"gc-02"',
        },
        group_imports=["./group-module.nix", "./shared-module.nix"],
        role_imports=["./role-module.nix"],
        host_imports=["./shared-module.nix", "./host-module.nix"],
    )

    exported = merged.export_host_config()

    assert exported["role_configs"] == {"custom-packages.enable": True}
    assert exported["nixos_configs"] == {
        "networking.firewall.allowedTCPPorts": [22, 443],
        "boot.kernel.sysctl.\"net.core.rmem_max\"": 8388608,
        "programs.zsh.enable": True,
        "nix.settings.max-jobs": '"auto"',
        "networking.hostName": '"gc-02"',
    }
    assert exported["import_configs"] == [
        "./group-module.nix",
        "./shared-module.nix",
        "./role-module.nix",
        "./host-module.nix",
    ]


def test_system_template_renders_ansible_driven_top_level_nixos(tmp_path):
    if shutil.which("nix-instantiate") is None:
        pytest.skip("nix-instantiate is not available")

    rendered = render_nix_template(
        "conf/nix-templates/systems/x86_64-linux/main",
        "default.nix.j2",
        {
            "role_configs": {"custom-packages.enable": True},
            "service_configs": {},
            "luxnix_configs": {"generic-settings.enable": True},
            "nixos_configs": {
                "networking.firewall.allowedTCPPorts": [22, 443],
                "networking.firewall.trustedInterfaces": ["wg0", "eth0"],
                "boot.kernel.sysctl.\"net.core.rmem_max\"": 16777216,
                "programs.zsh.enable": True,
            },
            "import_configs": ["./hardware-extra.nix"],
        },
    )
    output_file = tmp_path / "default.nix"
    write_nix_file(rendered, output_file)
    rendered = output_file.read_text()

    assert "./hardware-extra.nix" in rendered
    assert "networking.firewall.allowedTCPPorts = [ 22 443 ];" in rendered
    assert 'networking.firewall.trustedInterfaces = [ "wg0" "eth0" ];' in rendered
    assert 'boot.kernel.sysctl."net.core.rmem_max" = 16777216;' in rendered
    assert "programs.zsh.enable = true;" in rendered

    subprocess.run(
        ["nix-instantiate", "--parse", str(output_file)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
