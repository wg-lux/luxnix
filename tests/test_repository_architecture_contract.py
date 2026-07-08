from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text()


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


def test_host_entrypoints_keep_imports_local() -> None:
    for host_entrypoint in (REPO_ROOT / "systems/x86_64-linux").glob("*/default.nix"):
        text = host_entrypoint.read_text()
        match = re.search(r"imports\s*=\s*\[(.*?)\];", text, re.S)

        if match is None:
            continue

        imports_block = match.group(1)
        assert "modules/" not in imports_block, host_entrypoint
        assert "../" not in imports_block, host_entrypoint
