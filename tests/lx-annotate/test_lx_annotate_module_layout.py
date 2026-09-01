from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO_ROOT / "modules/nixos/services/lx-annotate-local"
SUBSERVICE_DIR = SERVICE_DIR / "subservices"
OPTIONS_DIR = SERVICE_DIR / "options"

EXPECTED_OPTION_GROUPS = {
    "center-admin-bootstrap": "centerAdminBootstrap",
    "database": "database",
    "data-cleanup": "dataCleanup",
    "data-recovery": "dataRecovery",
    "debug": "debug",
    "django": "django",
    "enable": "enable",
    "hls-backfill": "hlsBackfill",
    "hls-materialization": "hlsMaterialization",
    "hub": "hub",
    "runtime": "runtime",
    "source": "source",
    "storage-relief": "storageRelief",
    "streamable-migration": "streamableMigration",
}


def test_each_subservice_leaf_owns_one_documented_service() -> None:
    leaf_modules = sorted(
        path for path in SUBSERVICE_DIR.rglob("*.nix") if path.name != "workers.nix"
    )

    assert len(leaf_modules) == 37
    for module in leaf_modules:
        source = module.read_text(encoding="utf-8")
        relative_path = module.relative_to(SERVICE_DIR)
        assert source.startswith("# Purpose:"), relative_path
        assert "\n# Command:" in source, relative_path
        service_assignments = re.findall(
            r"^\s+(?:systemd\.)?services\.[A-Za-z0-9_-]+(?:\.serviceConfig)?\s*=",
            source,
            re.MULTILINE,
        )
        assert len(service_assignments) == 1, relative_path

    aggregator_source = (SUBSERVICE_DIR / "workers.nix").read_text(encoding="utf-8")
    config_source = (SERVICE_DIR / "config.nix").read_text(encoding="utf-8")
    assert "systemd.services." not in aggregator_source
    assert "systemd.services." not in config_source


def test_option_aggregator_exposes_one_readable_module_per_group() -> None:
    aggregator_source = (SERVICE_DIR / "options.nix").read_text(encoding="utf-8")
    option_modules = sorted(OPTIONS_DIR.glob("*.nix"))

    assert {path.stem for path in option_modules} == set(EXPECTED_OPTION_GROUPS)
    for module in option_modules:
        public_name = EXPECTED_OPTION_GROUPS[module.stem]
        source = module.read_text(encoding="utf-8")
        assert "options.services.luxnix.lxAnnotateLocal = {" in source
        assert len(re.findall(rf"^    {public_name} = ", source, re.MULTILINE)) == 1
        assert f"./options/{module.name}" in aggregator_source

    assert "options.services.luxnix.lxAnnotateLocal" not in aggregator_source
