from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def _nix_eval_json(expression: str) -> dict[str, Any]:
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression, "--show-trace"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _gc_02_terminology_contract() -> dict[str, Any]:
    return _nix_eval_json(f'''
      let
        flake = builtins.getFlake "git+file://{REPO_ROOT}";
        lib = flake.inputs.nixpkgs.lib;
        cfg = flake.nixosConfigurations.gc-02.config;
        lxCfg = cfg.services.luxnix.lxAnnotateLocal;
        env = cfg.systemd.services.lx-annotate.environment;
      in {{
        terminology = {{
          registryPath = lxCfg.runtime.terminology.registryPath;
          importRoot = lxCfg.runtime.terminology.importRoot;
          initialBundle = lxCfg.runtime.terminology.initialBundle;
        }};
        environment = {{
          registry = env.LX_DTYPES_KB_REGISTRY;
          importRoot = env.LX_DTYPES_TERMINOLOGY_IMPORT_ROOT;
        }};
        hasBootstrap = builtins.hasAttr "lx-annotate-terminology-bootstrap" cfg.systemd.services;
        migrate = {{
          after = cfg.systemd.services."lx-annotate-migrate".after;
          wants = cfg.systemd.services."lx-annotate-migrate".wants;
          requires = cfg.systemd.services."lx-annotate-migrate".requires;
        }};
        loadBaseData = {{
          after = cfg.systemd.services."lx-annotate-load-base-data".after;
          wants = cfg.systemd.services."lx-annotate-load-base-data".wants;
          requires = cfg.systemd.services."lx-annotate-load-base-data".requires;
        }};
        preflight = {{
          after = cfg.systemd.services."lx-annotate-preflight".after;
          requires = cfg.systemd.services."lx-annotate-preflight".requires;
        }};
        web = {{
          after = cfg.systemd.services.lx-annotate.after;
          wants = cfg.systemd.services.lx-annotate.wants;
          requires = cfg.systemd.services.lx-annotate.requires;
        }};
        acceptance = {{
          after = cfg.systemd.services."lx-annotate-acceptance".after;
          wants = cfg.systemd.services."lx-annotate-acceptance".wants;
          requires = cfg.systemd.services."lx-annotate-acceptance".requires;
        }};
        terminologyTmpfiles = builtins.filter
          (rule: lib.hasInfix "/terminology" rule)
          cfg.systemd.tmpfiles.rules;
      }}
    ''')


def _gc_02_repo_mode_contract() -> dict[str, Any]:
    return _nix_eval_json(f'''
      let
        flake = builtins.getFlake "git+file://{REPO_ROOT}";
        lib = flake.inputs.nixpkgs.lib;
        cfg = (flake.nixosConfigurations.gc-02.extendModules {{
          modules = [
            ({{ ... }}: {{
              services.luxnix.lxAnnotateLocal.runtime.mode = lib.mkForce "repo";
            }})
          ];
        }}).config;
        unitName = "lx-annotate-terminology-bootstrap";
      in {{
        hasBootstrap = builtins.hasAttr unitName cfg.systemd.services;
        loadBaseDataAfter = cfg.systemd.services."lx-annotate-load-base-data".after;
        webRequires = cfg.systemd.services.lx-annotate.requires;
        preflightRequires = cfg.systemd.services."lx-annotate-preflight".requires;
      }}
    ''')


def test_governed_terminology_paths_are_exported_inside_encrypted_storage() -> None:
    contract = _gc_02_terminology_contract()

    assert contract["terminology"] == {
        "registryPath": "/var/lib/lx-annotate/data/terminology/registry.json",
        "importRoot": "/var/lib/lx-annotate/data/terminology/packages",
        "initialBundle": None,
    }
    assert contract["environment"] == {
        "registry": contract["terminology"]["registryPath"],
        "importRoot": contract["terminology"]["importRoot"],
    }
    assert any("/terminology 0750" in rule for rule in contract["terminologyTmpfiles"])
    assert any("/terminology/packages 0750" in rule for rule in contract["terminologyTmpfiles"])


def test_retired_host_terminology_bootstrap_is_not_a_startup_gate() -> None:
    contract = _gc_02_terminology_contract()
    unit_name = "lx-annotate-terminology-bootstrap.service"
    assert contract["hasBootstrap"] is False
    assert "lx-annotate-migrate.service" in contract["loadBaseData"]["after"]
    assert "lx-annotate-migrate.service" in contract["loadBaseData"]["requires"]
    assert unit_name not in contract["loadBaseData"]["after"]
    assert unit_name not in contract["loadBaseData"]["wants"]
    assert unit_name not in contract["loadBaseData"]["requires"]
    assert unit_name not in contract["preflight"]["after"]
    assert unit_name not in contract["preflight"]["requires"]
    assert unit_name not in contract["web"]["after"]
    assert unit_name not in contract["web"]["wants"]
    assert unit_name not in contract["web"]["requires"]
    assert unit_name not in contract["acceptance"]["after"]
    assert unit_name not in contract["acceptance"]["wants"]
    assert unit_name not in contract["acceptance"]["requires"]


def test_repo_mode_does_not_require_wheel_only_terminology_bootstrap() -> None:
    contract = _gc_02_repo_mode_contract()
    unit_name = "lx-annotate-terminology-bootstrap.service"

    assert contract["hasBootstrap"] is False
    assert unit_name not in contract["loadBaseDataAfter"]
    assert unit_name not in contract["webRequires"]
    assert unit_name not in contract["preflightRequires"]
