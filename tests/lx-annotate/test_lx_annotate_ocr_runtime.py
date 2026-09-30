"""OCR dependencies must survive wheel deployment without a system profile link."""

import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


@pytest.mark.parametrize("custom_prefix", [None, "/srv/ocr/tessdata"])
def test_gc_02_ocr_runtime_contract(custom_prefix: str | None) -> None:
    override = (
        ""
        if custom_prefix is None
        else (
            "roles.endoreg-client.lxAnnotate.runtime.tessdataPrefix = "
            '"/srv/ocr/tessdata";'
        )
    )
    result = eval_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = (flake.nixosConfigurations.gc-02.extendModules {
            modules = [({ ... }: { OVERRIDE })];
          }).config;
          runtime = cfg.services.luxnix.lxAnnotateLocal.runtime;
          contract = name: let unit = cfg.systemd.services.${name}; in {
            prefix = unit.environment.TESSDATA_PREFIX;
            path = unit.environment.PATH;
          };
        in {
          package = toString runtime.tesseractPackage;
          prefix = runtime.tessdataPrefix;
          services = map contract [
            "lx-annotate"
            "lx-annotate-celery-worker"
            "lx-annotate-celery-pipeline-worker"
          ];
        }
        """.replace("OVERRIDE", override)
    )
    expected_prefix = custom_prefix or f"{result['package']}/share/tessdata"
    assert result["prefix"] == expected_prefix
    for service in result["services"]:
        assert service["prefix"] == expected_prefix
        assert f"{result['package']}/bin" in service["path"].split(":")


def test_wheel_maintenance_wrapper_provides_tesseract() -> None:
    source = (
        REPO_ROOT / "modules/nixos/services/lx-annotate-local/config.nix"
    ).read_text()
    wrapper = source.split('export PATH="${', 1)[1].split("}:", 1)[0]
    assert "cfg.runtime.tesseractPackage" in wrapper


def test_gc_02_tesseract_package_contains_required_languages() -> None:
    result = subprocess.run(
        [
            "nix",
            "build",
            "--no-link",
            "--print-out-paths",
            f"git+file://{REPO_ROOT}#nixosConfigurations.gc-02.config."
            "services.luxnix.lxAnnotateLocal.runtime.tesseractPackage",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    package = result.stdout.strip()
    languages = subprocess.run(
        [
            f"{package}/bin/tesseract",
            "--tessdata-dir",
            f"{package}/share/tessdata",
            "--list-langs",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert {"deu", "eng"} <= set(languages.stdout.splitlines())
