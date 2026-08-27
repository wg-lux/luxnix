from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_owning_derivations_install_standard_feature_roots() -> None:
    packages = {
        "lx-data-models": Path("/home/admin/lx-data-models/python-package.nix"),
        "endoreg-db": Path("/home/admin/endoreg-db/package.nix"),
        "lx-annotate": Path("/home/admin/dev/lx-annotate/package.nix"),
    }
    for provider, path in packages.items():
        source = path.read_text(encoding="utf-8")
        assert f"share/{provider}/features" in source


def test_package_specification_is_semantic_and_assessment_free() -> None:
    path = Path(
        "/home/admin/lx-data-models/features/PackagedKnowledgeBaseResources.yml"
    )
    specification = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert specification["id"] == "packaged_knowledge_base_resources"
    assert specification["invariants"]
    serialized = json.dumps(specification)
    assert "/nix/store" not in serialized
    assert "assessment" not in serialized
    assert "current_work" not in specification
    assert specification["id"] not in {"/nix/store", "site-packages"}


def test_package_exporters_whitelist_only_immutable_fields() -> None:
    for path in (
        Path("/home/admin/endoreg-db/package.nix"),
        Path("/home/admin/dev/lx-annotate/feature-package.nix"),
    ):
        source = path.read_text(encoding="utf-8")
        assert "top_keys" in source
        assert "requirement_keys" in source
        assert "yaml.safe_dump(specification" in source
        assert '"assessment"' not in source
        assert '"current_work"' not in source


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix is unavailable")
def test_lx_annotate_registry_uses_only_the_lightweight_feature_package() -> None:
    module = (
        ROOT / "modules/nixos/services/wg-lux-features/default.nix"
    ).read_text(encoding="utf-8")
    assert "package = pkgs.lx-annotate-feature-specifications;" in module
    assert "pkgs.lx-annotate." not in module
    assert "package = pkgs.lx-annotate;" not in module

    expression = f'''let
      basePkgs = import <nixpkgs> {{ system = "x86_64-linux"; }};
      featurePackage = basePkgs.runCommand "feature-only" {{ }}
        "mkdir -p $out/share/lx-annotate/features";
      pkgs = basePkgs.extend (_final: _prev: {{
        lx-annotate-feature-specifications = featurePackage;
        lx-annotate = throw "the full application package must not be evaluated";
      }});
      evaluated = import <nixpkgs/nixos> {{
        configuration = {{
          nixpkgs.pkgs = pkgs;
          imports = [ {ROOT}/modules/nixos/services/wg-lux-features/default.nix ];
          services.wg-lux-features.enable = true;
        }};
      }};
      selected =
        evaluated.config.services.wg-lux-features.providers.lx-annotate.package;
    in {{
      expected = featurePackage.outPath;
      selected = selected.outPath;
    }}'''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    outputs = json.loads(result.stdout)
    assert outputs["selected"] == outputs["expected"]


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix is unavailable")
def test_nixos_registry_uses_exact_configured_package_outputs(tmp_path: Path) -> None:
    expression = f'''let
      pkgs = import <nixpkgs> {{ system = "x86_64-linux"; }};
      packageA = pkgs.runCommand "provider-a" {{ }}
        "mkdir -p $out/share/example/features";
      packageB = pkgs.runCommand "provider-b" {{ }}
        "mkdir -p $out/share/example/features";
      evaluate = package: import <nixpkgs/nixos> {{
        configuration = {{ imports = [
          {ROOT}/modules/nixos/services/wg-lux-features/default.nix
          {{ services.wg-lux-features = {{
               enable = true;
               providers.example = {{
                 inherit package;
                 featureSubdir = "share/example/features";
                 revision = "revision-1";
                 version = "1.0";
               }};
             }};
          }}
        ]; }};
      }};
      inspect = package: let
        config = (evaluate package).config;
        provider = config.services.wg-lux-features.providers.example;
      in {{
        package_store_path = provider.package.outPath;
        feature_root = "${{provider.package}}/${{provider.featureSubdir}}";
        registry_source =
          toString config.environment.etc."wg-lux/features/providers.json".source;
      }};
    in {{ a = inspect packageA; b = inspect packageB; }}'''
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    registries = json.loads(result.stdout)
    provider_a = registries["a"]
    provider_b = registries["b"]
    assert provider_a["feature_root"].startswith(provider_a["package_store_path"])
    assert provider_a["package_store_path"] != provider_b["package_store_path"]
    assert provider_a["registry_source"] != provider_b["registry_source"]


def test_mcp_service_consumes_registry_without_checkout_fallback() -> None:
    module = (ROOT / "wg-lux-mcp/nixos/wg-lux-mcp.nix").read_text(encoding="utf-8")
    assert "WG_LUX_FEATURE_PROVIDER_REGISTRY" in module
    assert "WG_LUX_FEATURE_STATE_ROOT" in module
    assert "config.services.wg-lux-features.registryPath" in module
    assert "config.services.wg-lux-features.stateRoot" in module
    feature_tools = (
        ROOT / "wg-lux-mcp/src/wg_lux_mcp/tools/features.py"
    ).read_text(encoding="utf-8")
    assert "there is no checkout fallback" in feature_tools
    assert "subprocess" not in feature_tools
