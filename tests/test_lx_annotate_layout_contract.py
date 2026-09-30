import ast
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).parents[1]
LAYOUT = REPO_ROOT / "tests/lx-annotate/layout.yml"


def _test_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def test_lx_annotate_relocations_keep_or_explicitly_replace_every_test():
    manifest = yaml.safe_load(LAYOUT.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["canonical_directory"] == "tests/lx-annotate"
    for relocation in manifest["relocations"]:
        source = REPO_ROOT / relocation["source"]
        destination = REPO_ROOT / relocation["destination"]
        replacements = relocation.get("replacements", {})
        canonical_tests = _test_names(destination)

        assert not source.exists(), f"duplicate test suite remains: {source}"
        for previous_test in relocation["previous_tests"]:
            if previous_test in replacements:
                assert set(replacements[previous_test]) <= canonical_tests
            else:
                assert previous_test in canonical_tests
