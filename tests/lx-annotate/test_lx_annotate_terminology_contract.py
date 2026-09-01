from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "config.nix"
)


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
        flake = builtins.getFlake "path:{REPO_ROOT}";
        lib = flake.inputs.nixpkgs.lib;
        cfg = flake.nixosConfigurations.gc-02.config;
        lxCfg = cfg.services.luxnix.lxAnnotateLocal;
        bootstrap = cfg.systemd.services."lx-annotate-terminology-bootstrap";
        runtimePackage = cfg.services.lx-annotate.package;
        bootstrapEntrypoint = "${{runtimePackage}}/bin/lx-annotate-bootstrap-terminology";
        env = bootstrap.environment;
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
        bootstrap = {{
          before = bootstrap.before;
          after = bootstrap.after;
          requires = bootstrap.requires;
          wantedBy = bootstrap.wantedBy;
          serviceConfig = bootstrap.serviceConfig;
          unitConfig = bootstrap.unitConfig;
          script = builtins.readFile bootstrap.serviceConfig.ExecStart;
        }};
        bootstrapEntrypoint = {{
          path = bootstrapEntrypoint;
          script = builtins.readFile bootstrapEntrypoint;
        }};
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


def _gc_02_initial_bundle_script() -> str:
    return _nix_eval_json(f'''
      let
        flake = builtins.getFlake "path:{REPO_ROOT}";
        cfg = (flake.nixosConfigurations.gc-02.extendModules {{
          modules = [
            ({{ ... }}: {{
              services.luxnix.lxAnnotateLocal.runtime.terminology.initialBundle = {{
                inputDirectory = {REPO_ROOT}/tests;
                moduleName = "governed_test_bundle";
                version = "1.2.3";
                medicalField = "gastroenterology";
              }};
            }})
          ];
        }}).config;
      in {{
        script = builtins.readFile
          cfg.systemd.services."lx-annotate-terminology-bootstrap".serviceConfig.ExecStart;
      }}
    ''')["script"]


def _gc_02_repo_mode_contract() -> dict[str, Any]:
    return _nix_eval_json(f'''
      let
        flake = builtins.getFlake "path:{REPO_ROOT}";
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


def test_wheel_runtime_exports_executable_terminology_bootstrap_entrypoint() -> None:
    contract = _gc_02_terminology_contract()
    entrypoint = contract["bootstrapEntrypoint"]
    entrypoint_path = Path(entrypoint["path"])

    assert entrypoint_path.is_file()
    assert entrypoint_path.stat().st_mode & 0o111
    assert "LX_ANNOTATE_WHEEL_INSTALL_ALLOWED=false" in entrypoint["script"]
    assert "lx_annotate_wheel_ensure" in entrypoint["script"]
    assert '"lx-annotate-bootstrap-terminology" "$@"' in entrypoint["script"]

    config_source = CONFIG_NIX.read_text(encoding="utf-8")
    assert (
        "make_entrypoint lx-annotate-bootstrap-terminology "
        "lx-annotate-bootstrap-terminology 0"
    ) in config_source


def test_packaged_reporting_bundles_are_a_fail_closed_wheel_startup_gate() -> None:
    contract = _gc_02_terminology_contract()
    unit_name = "lx-annotate-terminology-bootstrap.service"
    bootstrap = contract["bootstrap"]
    script = bootstrap["script"]

    assert bootstrap["serviceConfig"]["Type"] == "oneshot"
    assert bootstrap["serviceConfig"]["RemainAfterExit"] is True
    assert bootstrap["serviceConfig"]["User"] == "endoreg-service-user"
    assert "/var/lib/lx-annotate/data" in bootstrap["unitConfig"]["RequiresMountsFor"]
    assert "lx-annotate-migrate.service" in bootstrap["before"]
    assert "lx-annotate.service" in bootstrap["before"]
    assert "lx-annotate-migrate.service" not in bootstrap["after"]
    assert "lx-annotate.service" not in bootstrap["after"]
    assert "lx-annotate-wheel-runtime.service" in bootstrap["after"]
    assert "lx-annotate-wheel-runtime.service" in bootstrap["requires"]
    assert "multi-user.target" in bootstrap["wantedBy"]
    assert "lx-annotate-bootstrap-terminology" in script
    assert "--registry" in script
    assert "--best-effort" not in script
    assert "lx-dtypes-kb-registry add-current" not in script
    assert "--activate" not in script

    assert unit_name in contract["migrate"]["after"]
    assert unit_name in contract["migrate"]["wants"]
    assert unit_name in contract["migrate"]["requires"]
    assert "lx-annotate-migrate.service" in contract["loadBaseData"]["after"]
    assert "lx-annotate-migrate.service" in contract["loadBaseData"]["requires"]
    assert unit_name not in contract["loadBaseData"]["after"]
    assert unit_name not in contract["loadBaseData"]["wants"]
    assert unit_name not in contract["loadBaseData"]["requires"]
    assert unit_name not in contract["preflight"]["after"]
    assert unit_name not in contract["preflight"]["requires"]
    assert unit_name in contract["web"]["after"]
    assert unit_name in contract["web"]["wants"]
    assert unit_name in contract["web"]["requires"]
    assert unit_name in contract["acceptance"]["after"]
    assert unit_name in contract["acceptance"]["wants"]
    assert unit_name in contract["acceptance"]["requires"]


def test_explicit_initial_bundle_is_passed_to_application_bootstrap() -> None:
    script = _gc_02_initial_bundle_script()

    assert "lx-annotate-bootstrap-terminology" in script
    assert "--module governed_test_bundle" in script
    assert "--version 1.2.3" in script
    assert "--medical-field gastroenterology" in script
    assert "--activate" not in script
    assert "lx-dtypes-kb-registry add-current" not in script


def test_repo_mode_does_not_require_wheel_only_terminology_bootstrap() -> None:
    contract = _gc_02_repo_mode_contract()
    unit_name = "lx-annotate-terminology-bootstrap.service"

    assert contract["hasBootstrap"] is False
    assert unit_name not in contract["loadBaseDataAfter"]
    assert unit_name not in contract["webRequires"]
    assert unit_name not in contract["preflightRequires"]
