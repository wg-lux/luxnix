from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOST = "gc-02"
INTAKE_ROOT = "/var/lib/lx-annotate/data/import"
INTAKE_DIRECTORY_NAMES = (
    "video_import",
    "report_import",
    "preanonymized_import",
    "sap_import",
    "sap_import_processed",
    "sap_import_failed",
)


def _tmpfiles_rules() -> list[str]:
    result = subprocess.run(
        [
            "nix",
            "eval",
            "--json",
            f".#nixosConfigurations.{HOST}.config.systemd.tmpfiles.rules",
            "--show-trace",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    rules = json.loads(result.stdout)
    assert isinstance(rules, list)
    return rules


def test_tmpfiles_eagerly_provisions_complete_protected_intake_contract() -> None:
    rules = _tmpfiles_rules()

    for directory_name in INTAKE_DIRECTORY_NAMES:
        path = f"{INTAKE_ROOT}/{directory_name}"
        assert f"d {path} 0770 endoreg-service-user endoreg-service - -" in rules
        assert f"z {path} 0770 endoreg-service-user endoreg-service - -" in rules


def test_sap_runtime_helpers_refuse_missing_intake_infrastructure() -> None:
    for relative_path in (
        "modules/nixos/services/lx-annotate-local/config.nix",
        "modules/nixos/services/lx-annotate-local/scripts.nix",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert 'install -d -m 0770 "$sap_drop_dir"' not in source
        assert "required SAP intake directory is missing" in source
