"""Exercise the same static contract used by build and service-user startup."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "modules/nixos/services/lx-annotate-local/scripts/wheel-static-check.py"
MANIFEST = {"src/main.ts": {"file": "main.js", "isEntry": True, "css": ["main.css"]}}


def run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(CHECK), *map(str, args)],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def wheel(tmp_path, manifest=MANIFEST, omit=None):
    target = tmp_path / "candidate.whl"
    with zipfile.ZipFile(target, "w") as archive:
        for name, content in {
            ".vite/manifest.json": json.dumps(manifest),
            "main.js": "export {};",
            "main.css": "body{}",
        }.items():
            if name != omit:
                archive.writestr("lx_annotate/staticfiles/" + name, content)
    return target


def test_checked_in_release_passes():
    result = run(
        "--wheel",
        ROOT / "release-artifacts/lx-annotate/1.2.2/lx_annotate-1.2.2-py3-none-any.whl",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        [],
        None,
        {"src/main.ts": None},
        {"src/main.ts": {"file": "main.js"}},
        {"src/main.ts": {"file": "../main.js", "isEntry": True}},
        {"src/main.ts": {"file": "/main.js", "isEntry": True}},
        {"src/main.ts": {"file": "main.js", "isEntry": True, "css": "main.css"}},
        {"src/main.ts": {"file": "main.js", "isEntry": True, "imports": ["absent"]}},
        {
            "src/main.ts": {
                "file": "main.js",
                "isEntry": True,
                "dynamicImports": ["absent"],
            }
        },
    ],
)
def test_rejects_invalid_manifest(tmp_path, manifest):
    result = run("--wheel", wheel(tmp_path, manifest))
    assert result.returncode == 1
    assert result.stdout == ""
    assert "static asset validation failed" in result.stderr


@pytest.mark.parametrize("omit", [".vite/manifest.json", "main.js", "main.css"])
def test_rejects_missing_asset(tmp_path, omit):
    assert run("--wheel", wheel(tmp_path, omit=omit)).returncode == 1


def installed(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    metadata = site / "lx_annotate-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: lx-annotate\nVersion: 1.0\n")
    package = site / "lx_annotate"
    package.mkdir()
    (package / "__init__.py").write_text(
        "raise RuntimeError('Django must not initialize')\n"
    )
    # An empty higher-priority directory must not hide a complete static tree.
    (package / "staticfiles").mkdir()
    assets = package / "static"
    (assets / ".vite").mkdir(parents=True)
    (assets / ".vite/manifest.json").write_text(json.dumps(MANIFEST))
    (assets / "main.js").write_text("export {};")
    (assets / "main.css").write_text("body{}")
    return assets, {**os.environ, "PYTHONPATH": str(site)}


def test_installed_discovery_has_only_path_output_and_does_not_import_app(tmp_path):
    assets, env = installed(tmp_path)
    result = run("--installed", env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(assets) + "\n"
    assert result.stderr == ""


def test_installed_rejects_escaping_symlink(tmp_path):
    assets, env = installed(tmp_path)
    outside = tmp_path / "outside.js"
    outside.write_text("export {};")
    (assets / "main.js").unlink()
    (assets / "main.js").symlink_to(outside)
    result = run("--installed", env=env)
    assert result.returncode == 1
    assert result.stdout == ""


def test_invalid_installed_assets_leave_served_tree_untouched(tmp_path):
    assets, env = installed(tmp_path)
    (assets / "main.css").unlink()
    served = tmp_path / "served"
    served.mkdir()
    (served / "previous.js").write_text("previous release")
    source = (CHECK.parent.parent / "config.nix").read_text()
    function = source.split("    lx_annotate_wheel_sync_static() {", 1)[1].split(
        "\n    }", 1
    )[0]
    replacements = {
        '${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/python"}': shlex.quote(
            sys.executable
        ),
        "${./scripts/wheel-static-check.py}": shlex.quote(str(CHECK)),
        '${lib.escapeShellArg "${runtimeStaticRootPath}/"}': shlex.quote(
            str(served) + "/"
        ),
        (
            '${lib.escapeShellArg "${runtimeStaticRootPath}/.vite/manifest.json"}'
        ): shlex.quote(str(served / ".vite/manifest.json")),
        "${lib.escapeShellArg runtimeStaticRootPath}": shlex.quote(str(served)),
    }
    for old, new in replacements.items():
        function = function.replace(old, new)
    result = subprocess.run(
        ["bash", "-c", "set -euo pipefail\ncheck() {" + function + "\n}\ncheck"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1, result.stderr
    assert "static asset validation failed" in result.stderr
    assert sorted(path.name for path in served.iterdir()) == ["previous.js"]
    assert (served / "previous.js").read_text() == "previous release"
