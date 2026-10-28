from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_intel_gpu_laptop_hardware_matches_pre_consolidation_configuration() -> None:
    import hashlib
    import json

    from lx_administration.models.ansible.inventory import AnsibleInventory
    from lx_administration.models.ansible.merged_host_vars import MergedHostVars

    # Snapshots of all effective Linux/GPU settings before moving host inputs.
    # Updating these requires reviewing the complete host hardware difference.
    expected = {
        "gc-04": "2e6c3f43c8acab0c4216843af4f386379861d9fb3065f38c8356982c9c2bd5d1",
        "gc-05": "07a3f36d995d7aa1833e7a38bd08d7b6918b4b2c2c9e0adbb39c6b6b70d3cb65",
        "gc-06": "576b2f731b0bc86db008582f9e2e5359eedc2a44c73a7f92843724c756c9095a",
        "gc-07": "a8d60c0d4a51ad31b5502b88d928ff9a5600fc4f16f055cd9fc43431a4297614",
        "gc-08": "a8d60c0d4a51ad31b5502b88d928ff9a5600fc4f16f055cd9fc43431a4297614",
        "gc-09": "07a3f36d995d7aa1833e7a38bd08d7b6918b4b2c2c9e0adbb39c6b6b70d3cb65",
        "gc-10": "2e6c3f43c8acab0c4216843af4f386379861d9fb3065f38c8356982c9c2bd5d1",
    }
    assert _inventory_group_members("intel_gpu_laptop") == set(expected)
    inventory = AnsibleInventory.load_from_hosts_ini(
        REPO_ROOT / "ansible/inventory/hosts.ini", subnet="172.16.255."
    )
    for hostname, digest in expected.items():
        settings = MergedHostVars.model_validate(
            inventory.export_merged_host_vars(hostname)
        ).prepare_luxnix()
        hardware = {
            key: value
            for key, value in settings.items()
            if key.startswith(("generic-settings.linux.", "generic-settings.gpu."))
            or key
            in ("generic-settings.hostPlatform", "generic-settings.systemStateVersion")
        }
        serialized = json.dumps(hardware, sort_keys=True).encode()
        actual = hashlib.sha256(serialized).hexdigest()
        assert actual == digest, hostname


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
        "modules/nixos/profiles/endoreg-gpu-client/default.nix": (
            "profiles.endoregGpuClient"
        ),
        "modules/nixos/profiles/endoreg-central-hub/default.nix": (
            "profiles.endoregCentralHub"
        ),
    }

    for relative_path, option_path in expected_profiles.items():
        profile = _read(relative_path)
        assert f"options.{option_path}" in profile
        assert "mkDefault" in profile


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_endoreg_profiles_inherit_policy_from_role_options() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = flake.inputs.nixpkgs.lib.extend (_: _: { luxnix = {}; });
        evaluate = profile: (lib.evalModules {
          modules = [
            ./modules/nixos/profiles/endoreg-client/default.nix
            ./modules/nixos/profiles/endoreg-central-hub/default.nix
            ({ lib, ... }: {
              options = {
                roles = lib.mkOption { type = lib.types.attrs; };
                services = lib.mkOption { type = lib.types.attrs; default = {}; };
              };
              config.profiles.${profile}.enable = true;
            })
          ];
        }).config;
        # Evaluate actual role API/database defaults with each profile's policy.
        policy = profile: (lib.evalModules {
          modules = [
            { options.enable = lib.mkEnableOption "role";
              options.api = import ./modules/nixos/roles/endoreg-client/api.nix {
                inherit lib;
              };
              options.database = lib.mkOption {
                type = lib.types.submodule
                  (import ./modules/nixos/roles/endoreg-client/database.nix {
                    inherit lib;
                  });
                default = {};
              };
            }
            (evaluate profile).roles.endoreg-client
          ];
        }).config;
      in builtins.mapAttrs (_: profile: policy profile) {
        client = "endoregClient"; hub = "endoregCentralHub";
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--json", "--impure", "--expr", expression],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    profiles = json.loads(result.stdout)
    assert profiles["client"] == profiles["hub"]
    assert profiles["client"]["enable"] is True
    assert profiles["client"]["api"]["useHttps"] is True


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
    # The package role no longer owns a second CUDA loader library list.
    assert "ldCuda" not in package_role
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

    template = _read("conf/nix-templates/systems/x86_64-linux/main/default.nix.j2")
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


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_role_controls_have_one_owner_and_allow_overrides() -> None:
    expression = r"""
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = f.inputs.nixpkgs.lib;
        evaluate = settings: (f.nixosConfigurations.gc-02.extendModules {
          modules = [ settings ];
        }).config;
        noDocker = evaluate { services.luxnix.podman.dockerDropIn = false; };
        noPodman = evaluate { services.luxnix.podman.enable = false; };
        legacy = evaluate { services.virtualisation.podman.enable = false; };
        generic = evaluate {
          luxnix.generic-settings.virtualization.podman.enable = false;
        };
        network = evaluate {
          luxnix.generic-settings.virtualization.podman.dnsEnabled = false;
          luxnix.generic-settings.virtualization.podman.socketEnable = false;
          luxnix.generic-settings.virtualization.podman.extraConfig = {
            internal = true;
          };
        };
        programs = evaluate {
          cli.programs.nix-ld.enable = false;
          programs.thunderbird.enable = true;
          programs.obs-studio.enable = true;
        };
        # Isolate the actual base-server module from this host's desktop choices.
        base = (lib.evalModules {
          modules = [
            ./modules/nixos/roles/base-server/default.nix
            { options = {
                roles.common.enable = lib.mkEnableOption "common";
                roles.custom-packages.baseDevelopment = lib.mkEnableOption "tools";
                roles.desktop.enable = lib.mkEnableOption "desktop";
                services = lib.mkOption { type = lib.types.attrs; default = {}; };
              };
              config.roles.base-server.enable = true;
            }
          ];
          specialArgs.lib = lib.extend (_: _: { luxnix = {}; });
        }).config;
        proxy = settings: (f.nixosConfigurations.s-02.extendModules {
          modules = [
            { roles.nginxHost.glm52.domain = "proxy.example.invalid"; } settings
          ];
        }).config.roles.nginxHost.glm52;
        headless = (f.nixosConfigurations.s-01.extendModules {
          modules = [ { roles.desktop.enable = lib.mkForce false; } ];
        }).config;
      in {
        docker = [ noDocker.virtualisation.podman.enable
          noDocker.virtualisation.podman.dockerCompat
          noDocker.virtualisation.podman.dockerSocket.enable
          noDocker.virtualisation.podman.defaultNetwork.settings.dns_enabled ];
        disabled = [ noPodman.virtualisation.podman.enable
          legacy.virtualisation.podman.enable generic.virtualisation.podman.enable ];
        network = [ network.virtualisation.podman.defaultNetwork.settings.dns_enabled
          network.virtualisation.podman.defaultNetwork.settings.internal
          network.virtualisation.podman.dockerSocket.enable ];
        programs = [ programs.programs.nix-ld.enable
          programs.programs.thunderbird.enable
          programs.programs.obs-studio.enable ];
        base = [ base.roles.common.enable base.roles.desktop.enable
          base.roles.custom-packages.baseDevelopment ];
        headless = [ headless.services.desktopManager.plasma6.enable
          headless.hardware.audio.enable headless.hardware.bluetooth.enable ];
        callback = (proxy {}).oauth2.redirectURL;
        explicitCallback = (proxy {
          roles.nginxHost.glm52.oauth2.redirectURL = "https://login.example.invalid/callback";
        }).oauth2.redirectURL;
        retiredCuda = builtins.hasAttr "cuda"
          f.nixosConfigurations.gc-02.options.roles.custom-packages;
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["docker"] == [True, False, False, True]
    assert data["disabled"] == [False, False, False]
    assert data["network"] == [False, True, False]
    assert data["programs"] == [False, True, True]
    assert data["base"] == [True, False, True]
    assert data["headless"] == [False, False, False]
    assert data["callback"] == "https://proxy.example.invalid/oauth2/callback"
    assert data["explicitCallback"] == "https://login.example.invalid/callback"
    assert data["retiredCuda"] is False


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_nextcloud_uses_supported_sequential_upgrade_package() -> None:
    expression = r"""
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        host = f.nixosConfigurations.s-03;
        selected = host.config.services.nextcloud.package;
      in {
        enabled = host.config.services.nextcloud.enable;
        version = selected.version;
        vulnerabilities = selected.meta.knownVulnerabilities;
        matchesRole = selected.drvPath
          == host.config.roles.nextcloudHost.package.drvPath;
        matchesDefault = selected.drvPath
          == host.options.roles.nextcloudHost.package.default.drvPath;
        matchesPinned = selected.drvPath == host.pkgs.nextcloud33.drvPath;
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["enabled"] is True
    assert data["version"].startswith("33.")
    assert data["vulnerabilities"] == []
    assert data["matchesRole"] and data["matchesDefault"] and data["matchesPinned"]
