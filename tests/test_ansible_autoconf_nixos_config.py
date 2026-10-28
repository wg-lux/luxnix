import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from lx_administration.autoconf.imports.sources import load_home_host_vars
from lx_administration.autoconf.nix.home_template_renderer import (
    render_home_nix_template,
    to_nix,
)
from lx_administration.autoconf.nix.template_renderer import (
    nix_literal,
    nix_string,
    render_nix_template,
    split_attr_path,
)
from lx_administration.autoconf.nix.utils import write_nix_file
from lx_administration.models import MergedHostVars
from lx_administration.models.ansible import AnsibleInventory

REPO_ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (True, "true"),
        (None, "null"),
        (42, "42"),
        ("english", '"english"'),
        ('"x86_64-linux"', '"x86_64-linux"'),
        (["one", "two"], '[ "one" "two" ]'),
        ({"enable": True}, "{ enable = true; }"),
        ("[Match]\nName = eth0\n", '"[Match]\nName = eth0\n"'),
    ),
)
def test_nix_literal_contract(value, expected) -> None:
    assert nix_literal(value) == expected


def test_nix_literal_rejects_unknown_python_types() -> None:
    with pytest.raises(TypeError, match="Unsupported Nix literal type: tuple"):
        nix_literal(("not", "a", "yaml-list"))


def test_nix_string_preserves_numeric_looking_versions() -> None:
    assert nix_string("24.05") == '"24.05"'


def test_home_renderer_uses_the_shared_literal_contract(tmp_path) -> None:
    (tmp_path / "value.nix.j2").write_text("{{ value | to_nix }}", encoding="utf-8")

    rendered = render_home_nix_template(
        tmp_path,
        "value.nix.j2",
        {"value": ["one", "two"]},
    )

    assert to_nix is nix_literal
    assert rendered == '[ "one" "two" ]'


def test_home_renderer_uses_the_explicit_state_version() -> None:
    template_dir = REPO_ROOT / "conf/nix-templates/homes/x86_64-linux"
    config = MergedHostVars().prepare_home_config(
        "admin",
        state_version="24.05",
    )

    rendered = render_home_nix_template(
        template_dir,
        "default.nix.j2",
        config,
    )

    assert 'home.stateVersion = "24.05";' in rendered
    assert 'home.stateVersion = "23.11";' not in rendered


def test_current_home_inventory_renders_as_parseable_nix(tmp_path) -> None:
    if shutil.which("nix-instantiate") is None:
        pytest.skip("nix-instantiate is not available")

    inventory_dir = REPO_ROOT / "ansible/inventory"
    template_dir = REPO_ROOT / "conf/nix-templates/homes/x86_64-linux"

    for hostname, values in load_home_host_vars(inventory_dir).items():
        merged = MergedHostVars(**values)
        rendered = render_home_nix_template(
            template_dir,
            "default.nix.j2",
            merged.prepare_home_config("admin", state_version="23.11"),
        )
        output = tmp_path / f"{hostname}.nix"
        output.write_text(rendered, encoding="utf-8")

        parsed = subprocess.run(
            ["nix-instantiate", "--parse", output],
            check=False,
            capture_output=True,
            text=True,
        )
        assert parsed.returncode == 0, f"{hostname}: {parsed.stderr}"


def test_c01_home_source_declares_both_managed_users() -> None:
    values = load_home_host_vars(REPO_ROOT / "ansible/inventory")["c-01"]
    merged = MergedHostVars(**values)

    assert merged.system_users == ["admin", "client-user"]


def test_merged_host_vars_defaults_are_not_shared() -> None:
    first = MergedHostVars()
    second = MergedHostVars()

    first.group_roles["changed"] = True
    first.group_imports.append("./changed.nix")

    assert second.group_roles == {}
    assert second.group_imports == []


def test_merged_host_vars_loaders_select_their_documented_fields(tmp_path) -> None:
    source = tmp_path / "merged.yml"
    source.write_text(
        """
group_roles:
  system.enable: true
host_home_roles:
  home.enable: true
""",
        encoding="utf-8",
    )

    system_vars = MergedHostVars.load_from_file(source)
    home_vars = MergedHostVars.load_home_from_file(source)

    assert system_vars.group_roles == {"system.enable": True}
    assert system_vars.host_home_roles == {}
    assert system_vars.system_users == ["admin"]
    assert home_vars.group_roles == {}
    assert home_vars.host_home_roles == {"home.enable": True}
    assert home_vars.system_users == []


@pytest.mark.parametrize("loader_name", ("load_from_file", "load_home_from_file"))
def test_merged_host_vars_loaders_reject_non_mapping_yaml(
    tmp_path, loader_name
) -> None:
    source = tmp_path / "merged.yml"
    source.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    loader = getattr(MergedHostVars, loader_name)

    with pytest.raises(ValueError, match="Expected a YAML mapping"):
        loader(source)


@pytest.mark.parametrize(
    "loader",
    (
        AnsibleInventory.from_file,
        MergedHostVars.load_from_file,
        MergedHostVars.load_home_from_file,
    ),
)
def test_ansible_model_loaders_reject_duplicate_keys_with_path(tmp_path, loader):
    source = tmp_path / "ambiguous.yml"
    source.write_text("file: first\nfile: shadowed\n", encoding="utf-8")

    with pytest.raises(yaml.YAMLError, match="duplicate key 'file'") as error:
        loader(source)

    assert str(source) in str(error.value)


def test_inventory_loader_reports_missing_file_without_assert(tmp_path):
    missing = tmp_path / "missing.yml"

    with pytest.raises(FileNotFoundError, match="Inventory file not found"):
        AnsibleInventory.from_file(missing)


def test_merged_host_vars_uses_group_role_host_precedence() -> None:
    merged = MergedHostVars(
        group_services={"service": {"source": "group", "group": True}},
        role_services={"service": {"source": "role", "role": True}},
        host_services={"service": {"source": "host", "host": True}},
    )

    assert merged.prepare_services() == {
        "service": {
            "source": "host",
            "group": True,
            "role": True,
            "host": True,
        }
    }


def test_merged_host_vars_exports_top_level_nixos_and_imports():
    merged = MergedHostVars(
        group_roles={"custom_packages.enable": True},
        group_nixos={
            "networking.firewall.allowedTCPPorts": [22],
            'boot.kernel.sysctl."net.core.rmem_max"': 8388608,
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
        'boot.kernel.sysctl."net.core.rmem_max"': 8388608,
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
            "hostname": "node-01",
            "role_configs": {"custom-packages.enable": True},
            "service_configs": {},
            "luxnix_configs": {"generic-settings.enable": True},
            "nixos_configs": {
                "networking.firewall.allowedTCPPorts": [22, 443],
                "networking.firewall.trustedInterfaces": ["wg0", "eth0"],
                'boot.kernel.sysctl."net.core.rmem_max"': 16777216,
                "programs.zsh.enable": True,
            },
            "import_configs": ["./hardware-extra.nix"],
        },
    )
    output_file = tmp_path / "default.nix"
    write_nix_file(rendered, output_file)
    rendered = output_file.read_text()

    assert rendered.startswith("# node-01/default.nix")
    assert "../host-common.nix" in rendered
    assert "ansible.enable" not in rendered
    assert "settings.mutable" not in rendered
    assert "./hardware-extra.nix" in rendered
    assert (
        """  networking.firewall = {
    allowedTCPPorts = [
      22
      443
    ];
    trustedInterfaces = [
      "wg0"
      "eth0"
    ];
  };"""
        in rendered
    )
    assert '  boot.kernel.sysctl."net.core.rmem_max" = 16777216;' in rendered
    assert "  programs.zsh.enable = true;" in rendered

    subprocess.run(
        ["nix-instantiate", "--parse", str(output_file)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def test_system_template_preserves_nested_lists_in_raw_service_expressions(
    tmp_path,
):
    if shutil.which("nix-instantiate") is None:
        pytest.skip("nix-instantiate is not available")

    nodes = (
        '[ { identity = "storage-01"; '
        'artifactKinds = [ "video" "manifest" ]; '
        'endpoint = "https://storage-01:9443"; } ]'
    )
    rendered = render_nix_template(
        "conf/nix-templates/systems/x86_64-linux/main",
        "default.nix.j2",
        {
            "hostname": "hub-01",
            "role_configs": {},
            "service_configs": {"luxnix.hubStorage.hubClient.nodes": nodes},
            "luxnix_configs": {},
            "nixos_configs": {},
            "import_configs": [],
        },
    )
    output_file = tmp_path / "default.nix"
    write_nix_file(rendered, output_file)

    assert 'artifactKinds = [ "video" "manifest" ];' in rendered
    assert rendered.count("[ ") >= 2
    subprocess.run(
        ["nix-instantiate", "--parse", str(output_file)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def test_system_template_layers_paths_nested_below_an_expression(tmp_path):
    if shutil.which("nix-instantiate") is None:
        pytest.skip("nix-instantiate is not available")

    rendered = render_nix_template(
        "conf/nix-templates/systems/x86_64-linux/main",
        "default.nix.j2",
        {
            "hostname": "node-01",
            "role_configs": {},
            "service_configs": {},
            "luxnix_configs": {
                "storage.bindMounts": 'lib.recursiveUpdate { "/a" = 1; } { "/b" = 2; }',
                'storage.bindMounts."/c"': 3,
                "storage.enable": True,
            },
            "nixos_configs": {},
            "import_configs": [],
        },
    )
    output_file = tmp_path / "default.nix"
    write_nix_file(rendered, output_file)

    assert "lib.foldl' lib.recursiveUpdate" in rendered
    base, overlay = rendered.split("# Paths nested below an option set above")
    assert "luxnix.storage = {" in base
    assert "    enable = true;" in base
    assert 'luxnix.storage.bindMounts."/c" = 3;' in overlay
    evaluated = subprocess.run(
        [
            "nix-instantiate",
            "--eval",
            "--strict",
            "--json",
            "--expr",
            # Minimal stand-in for nixpkgs lib so the test needs no NIX_PATH.
            "let recursiveUpdate = a: b: a // builtins.mapAttrs (n: v: "
            "if builtins.isAttrs v && builtins.isAttrs (a.${n} or null) "
            "then recursiveUpdate a.${n} v else v) b; "
            "lib = { inherit recursiveUpdate; foldl' = builtins.foldl'; }; in "
            f"(import {output_file} {{ inherit lib; pkgs = null; modulesPath = /.; }})"
            ".luxnix.storage.bindMounts",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert evaluated.stdout.strip() == '{"/a":1,"/b":2,"/c":3}'


def test_system_template_without_nested_paths_is_a_plain_attribute_set():
    rendered = render_nix_template(
        "conf/nix-templates/systems/x86_64-linux/main",
        "default.nix.j2",
        {
            "hostname": "node-01",
            "role_configs": {"common.enable": True},
            "service_configs": {},
            "luxnix_configs": {"dns.enable": True},
            "nixos_configs": {},
            "import_configs": [],
        },
    )

    assert "recursiveUpdate" not in rendered
    assert "  roles.common.enable = true;\n\n  luxnix.dns.enable = true;" in rendered


def test_system_template_binds_each_key_once_per_attribute_set():
    rendered = render_nix_template(
        "conf/nix-templates/systems/x86_64-linux/main",
        "default.nix.j2",
        {
            "hostname": "node-01",
            "role_configs": {
                "custom-packages.enable": True,
                "custom-packages.cloud": True,
                "common.enable": True,
            },
            "service_configs": {},
            "luxnix_configs": {},
            "nixos_configs": {"services.openssh.enable": True},
            "import_configs": [],
        },
    )

    assert (
        """  roles = {
    common.enable = true;

    custom-packages = {
      cloud = true;
      enable = true;
    };
  };"""
        in rendered
    )
    # Top-level NixOS options merge into the matching namespace.
    assert "  services.openssh.enable = true;" in rendered
    assert rendered.count("services") == 1


def test_system_template_rejects_duplicate_option_paths():
    with pytest.raises(ValueError, match="Duplicate Nix option path"):
        render_nix_template(
            "conf/nix-templates/systems/x86_64-linux/main",
            "default.nix.j2",
            {
                "hostname": "node-01",
                "role_configs": {},
                "service_configs": {"openssh.enable": True},
                "luxnix_configs": {},
                "nixos_configs": {"services.openssh.enable": False},
                "import_configs": [],
            },
        )


@pytest.mark.parametrize(
    ("path", "segments"),
    (
        ("a.b", ("a", "b")),
        ('sysctl."net.core.rmem_max"', ("sysctl", '"net.core.rmem_max"')),
        ('hosts."${config.vault.vpnIp}".x', ("hosts", '"${config.vault.vpnIp}"', "x")),
        ('ops."spiffe://endoreg/hub/gs-02"', ("ops", '"spiffe://endoreg/hub/gs-02"')),
    ),
)
def test_split_attr_path_keeps_quoted_segments(path, segments):
    assert split_attr_path(path) == segments


@pytest.mark.parametrize("path", ("a..b", 'a."b', "a.", 'a."${x".b'))
def test_split_attr_path_rejects_malformed_paths(path):
    with pytest.raises(ValueError):
        split_attr_path(path)
