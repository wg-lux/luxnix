from __future__ import annotations

import copy
from pathlib import Path
import runpy

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHECK = runpy.run_path(str(ROOT / "scripts/check-secret-rotation.py"))


def source_tree(tmp_path):
    catalog = yaml.safe_load((ROOT / "secrets-management.yml").read_text())
    roots = {name: tmp_path / name for name in catalog["repositories"]}
    references = {
        name: [manifest] for name, manifest in catalog["repositories"].items()
    }
    references["luxnix"] += [catalog["readiness"], catalog["runbook"]]
    for family in catalog["families"].values():
        for repository, paths in family["contracts"].items():
            references[repository] += paths
    for repository, paths in references.items():
        for relative in paths:
            path = roots[repository] / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    path = tmp_path / "catalog.yml"
    path.write_text(yaml.safe_dump(catalog))
    return catalog, roots, path


def test_catalog_validates_all_repository_contracts(tmp_path):
    catalog, roots, path = source_tree(tmp_path)
    result = CHECK["check_catalog"](path, roots)
    assert set(result.families) == set(catalog["families"])
    (roots["lx_annotate"] / "lx_annotate/settings/config.py").unlink()
    with pytest.raises(ValueError, match="missing or external"):
        CHECK["check_catalog"](path, roots)


@pytest.mark.parametrize(
    "failure",
    [
        "order",
        "missing_gate",
        "unknown_field",
        "missing_repo",
        "empty_contract",
        "absolute",
        "escape",
        "duplicate",
    ],
)
def test_catalog_rejects_ambiguous_or_incomplete_contracts(tmp_path, failure):
    catalog, roots, path = source_tree(tmp_path)
    data = copy.deepcopy(catalog)
    if failure == "order":
        data["phases"].reverse()
    elif failure == "missing_gate":
        data["phases"].remove("verify")
    elif failure == "unknown_field":
        data["execute"] = True
    elif failure == "missing_repo":
        del data["repositories"]["endoreg_db"]
    elif failure == "empty_contract":
        data["families"]["django_signing"]["contracts"]["lx_annotate"] = []
    elif failure in {"absolute", "escape"}:
        data["runbook"] = str(path) if failure == "absolute" else "../catalog.yml"
    path.write_text(
        yaml.safe_dump(data) + ("schema_version: 1\n" if failure == "duplicate" else "")
    )
    with pytest.raises((ValueError, yaml.YAMLError)):
        CHECK["check_catalog"](path, roots)


def test_catalog_rejects_external_symlink(tmp_path):
    _, roots, path = source_tree(tmp_path)
    manifest = roots["endoreg_db"] / "structure.yml"
    manifest.unlink()
    manifest.symlink_to(path)
    with pytest.raises(ValueError, match="missing or external"):
        CHECK["check_catalog"](path, roots)


def test_catalog_is_registered_in_canonical_maps():
    project = yaml.safe_load((ROOT / "luxnix.yml").read_text())
    commands = yaml.safe_load((ROOT / "devenv/commands.yml").read_text())
    assert project["paths"]["secret_rotation_catalog"] == "secrets-management.yml"
    command = next(
        item for item in commands["commands"] if item["id"] == "check-secret-rotation"
    )
    assert command["risk"] == "read-only"
    assert command["operator_confirmation_required"] is False
    assert (ROOT / command["implementation"]).is_file()
