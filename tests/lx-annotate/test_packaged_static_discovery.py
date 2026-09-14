from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("source_name", ["config.nix", "scripts.nix"])
@pytest.mark.parametrize("asset_directory", ["staticfiles", "static", None])
def test_static_discovery_does_not_initialize_django(
    tmp_path: Path, source_name: str, asset_directory: str | None
) -> None:
    source = (
        ROOT / "modules/nixos/services/lx-annotate-local" / source_name
    ).read_text()
    locator = source.split('package_static_dir="$(')[1]
    match = re.search(r"<<'PY'\n(.*?)\n\s*PY\n", locator, re.DOTALL)
    assert match is not None
    snippet = textwrap.dedent(match.group(1))

    package = tmp_path / "lx_annotate"
    package.mkdir()
    (package / "__init__.py").write_text(
        'print("Django startup output must not become a filesystem path")\n'
        'raise RuntimeError("Static discovery must not initialize Django")\n'
    )
    metadata = tmp_path / "lx_annotate-1.2.2.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: lx-annotate\nVersion: 1.2.2\n"
    )
    if asset_directory:
        (package / asset_directory).mkdir()

    result = subprocess.run(
        [sys.executable, "-S", "-c", snippet],
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = f"{package / asset_directory}\n" if asset_directory else ""
    assert result.stdout == expected
    assert result.stderr == ""
