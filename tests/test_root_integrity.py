"""Evaluate the prototype against an isolated source fixture, never private files."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_image_dependency_excludes_unrelated_source_files(tmp_path):
    helper = tmp_path / "lx_administration/storage/openbao_local.py"
    helper.parent.mkdir(parents=True)
    helper.write_bytes((ROOT / "lx_administration/storage/openbao_local.py").read_bytes())
    unrelated = tmp_path / "unrelated.txt"
    unrelated.write_text("first revision")
    expression = r'''
      let
        f = builtins.getFlake ("git+file://" + toString ./.);
        test = f.inputs.nixpkgs.legacyPackages.x86_64-linux.testers.runNixOSTest
          (import (f.outPath + "/tests/nixtest/root_integrity_vm_test.nix") {
            repoRoot = builtins.toPath SOURCE;
          });
        c = test.nodes.machine;
      in {
        source = toString c.environment.etc."luxnix-openbao-local.py".source;
        image = c.system.build.image.drvPath;
      }
    '''.replace("SOURCE", json.dumps(str(tmp_path)))

    def evaluate():
        result = subprocess.run(
            ["nix", "eval", "--impure", "--json", "--expr", expression],
            cwd=ROOT, capture_output=True, text=True, timeout=240, check=True,
        )
        return json.loads(result.stdout)

    before = evaluate()
    unrelated.write_text("unrelated local data must not enter the image")
    assert evaluate() == before
    assert before["source"] == str(helper)
