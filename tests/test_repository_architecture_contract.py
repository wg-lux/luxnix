from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


def _inventory_group_members(group: str) -> set[str]:
    members: set[str] = set()
    current_group = ""
    for raw_line in _read("ansible/inventory/hosts.ini").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_group = line[1:-1]
        elif current_group == group:
            members.add(line.split()[0])
    return members


def test_snowfall_layout_contract_is_declared() -> None:
    flake = _read("flake.nix")

    assert "snowfall-lib" in flake
    assert 'namespace = "luxnix";' in flake

    for relative_path in [
        "systems",
        "homes",
        "modules/nixos",
        "modules/home",
        "packages",
        "overlays",
    ]:
        assert (REPO_ROOT / relative_path).is_dir()


def test_reusable_profiles_define_project_options() -> None:
    expected_profiles = {
        "modules/nixos/profiles/endoreg-client/default.nix": "profiles.endoregClient",
        "modules/nixos/profiles/endoreg-gpu-client/default.nix": "profiles.endoregGpuClient",
        "modules/nixos/profiles/endoreg-central-hub/default.nix": "profiles.endoregCentralHub",
    }

    for relative_path, option_path in expected_profiles.items():
        profile = _read(relative_path)
        assert f"options.{option_path}" in profile
        assert "mkDefault" in profile


def test_common_development_bucket_contains_introspection_tools() -> None:
    module = _read("modules/nixos/roles/custom-packages/default.nix")
    match = re.search(r"baseDevelopment = with pkgs; \[(.*?)\];", module, re.S)

    assert match is not None

    base_development = match.group(1)
    for package in [
        "ripgrep",
        "fd",
        "duf",
        "dust",
        "dysk",
        "ncdu",
        "nix-tree",
        "nixos-shell",
        "nix-output-monitor",
    ]:
        assert re.search(rf"\b{re.escape(package)}\b", base_development)


def test_nix_ld_library_ownership_is_not_duplicated() -> None:
    cli_module = _read("modules/nixos/cli/programs/nix-ld/default.nix")
    package_role = _read("modules/nixos/roles/custom-packages/default.nix")
    base_server = _read("modules/nixos/roles/base-server/default.nix")

    assert "extraLibraries" in cli_module
    assert "cfg.libraries ++ cfg.extraLibraries" in cli_module
    assert "ldBase" not in package_role
    assert "extraLibraries = optionals cfg.cuda ldCuda;" in package_role
    assert "cli.programs.nix-ld" not in base_server


def test_custom_package_role_has_no_empty_bundle_options() -> None:
    module = _read("modules/nixos/roles/custom-packages/default.nix")

    assert "dev01" not in module
    assert "dev02" not in module


def test_service_modules_only_install_required_client_packages() -> None:
    nfs_module = _read("modules/nixos/services/nfs/default.nix")
    postgres_module = _read("modules/nixos/services/postgres/default.nix")

    assert "cifs-utils" in nfs_module
    assert "nfs-utils" not in nfs_module
    assert "environment.systemPackages" not in postgres_module
    assert "package = pkgs.postgresql_16_jit;" in postgres_module


def test_host_entrypoints_keep_imports_local() -> None:
    for host_entrypoint in (REPO_ROOT / "systems/x86_64-linux").glob("*/default.nix"):
        text = host_entrypoint.read_text()
        match = re.search(r"imports\s*=\s*\[(.*?)\];", text, re.S)

        if match is None:
            continue

        imports_block = match.group(1)
        assert "modules/" not in imports_block, host_entrypoint
        parent_imports = re.findall(r"\.\./[^\s]+", imports_block)
        assert parent_imports in ([], ["../host-common.nix"]), host_entrypoint


def test_autoconf_hosts_use_one_shared_host_baseline() -> None:
    systems = REPO_ROOT / "systems/x86_64-linux"
    managed_entrypoints = sorted(
        path for path in systems.glob("*/default.nix") if path.parent.name != "lx-test"
    )

    assert managed_entrypoints
    for entrypoint in managed_entrypoints:
        text = entrypoint.read_text(encoding="utf-8")
        assert text.count("../host-common.nix") == 1, entrypoint
        assert "ansible.enable" not in text, entrypoint
        assert "settings.mutable" not in text, entrypoint

    isolated_test_host = (systems / "lx-test/default.nix").read_text(encoding="utf-8")
    assert "../host-common.nix" not in isolated_test_host

    shared = (systems / "host-common.nix").read_text(encoding="utf-8")
    assert 'admin.name = "admin";' in shared
    assert "ansible.enable = true;" in shared
    assert "settings.mutable = false;" in shared

    template = _read(
        "conf/nix-templates/systems/x86_64-linux/main/default.nix.j2"
    )
    assert template.count("../host-common.nix") == 1
    assert "ansible.enable" not in template
    assert "settings.mutable" not in template


def test_machine_specific_files_do_not_enable_services_or_roles() -> None:
    systems = REPO_ROOT / "systems/x86_64-linux"
    forbidden_setting = re.compile(r"^\s*(?:services|roles|profiles|user)\.", re.M)

    for pattern in ("*/disks.nix", "*/boot-decryption-config.nix"):
        for machine_file in systems.glob(pattern):
            text = machine_file.read_text(encoding="utf-8")
            assert forbidden_setting.search(text) is None, machine_file


def test_exported_host_names_follow_the_active_inventory() -> None:
    systems = REPO_ROOT / "systems/x86_64-linux"
    configured_hosts = {
        path.parent.name
        for path in systems.glob("*/default.nix")
        if path.parent.name != "lx-test"
    }

    assert configured_hosts == _inventory_group_members("active_clients")

    topology = _read("topology/default.nix")
    assert "nixosConfigurations" in _read("flake.nix")
    for host in configured_hosts:
        assert host not in topology


def test_gs_02_volatile_redis_follow_up_has_a_durable_reference() -> None:
    inventory = _read("ansible/inventory/host_vars/gs-02.yml")
    runbook = "docs/operations/gs-02-local-redis-broker.md"

    assert runbook in inventory
    assert (REPO_ROOT / runbook).is_file()
