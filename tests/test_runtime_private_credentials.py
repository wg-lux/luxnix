"""Exercise the runtime credential publication shell with synthetic inputs."""

import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def publish(source, target):
    text = (ROOT / "modules/nixos/services/lx-annotate-local/config.nix").read_text()
    helper = (
        "copy_private_credential() ("
        + text.split("copy_private_credential() (", 1)[1].split("\n    )", 1)[0]
        + "\n)"
    )
    helper = helper.replace("${endoreg-service-user-name}", str(os.getuid()))
    helper = helper.replace("${endoreg-service-group-name}", str(os.getgid()))
    return subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            helper + '\ncopy_private_credential "$1" "$2"',
            "test",
            str(source),
            str(target),
        ],
        capture_output=True,
    )


def test_publishes_private_copy_without_changing_source(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"synthetic-test-credential\n")
    source.chmod(0o640)
    target.write_bytes(b"previous-test-credential")
    assert publish(source, target).returncode == 0
    assert target.read_bytes() == source.read_bytes()
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.stat().st_uid == os.getuid()
    assert source.stat().st_mode & 0o777 == 0o640
    assert not list(tmp_path.glob("target.*"))


@pytest.mark.parametrize("kind", ["missing", "empty", "directory", "symlink"])
def test_invalid_source_preserves_previous_private_copy(tmp_path, kind):
    source, target = tmp_path / "source", tmp_path / "target"
    target.write_bytes(b"existing-test-credential")
    target.chmod(0o600)
    if kind == "empty":
        source.touch()
    elif kind == "directory":
        source.mkdir()
    elif kind == "symlink":
        source.symlink_to(target)
    result = publish(source, target)
    assert result.returncode != 0
    assert target.read_bytes() == b"existing-test-credential"
    assert target.stat().st_mode & 0o777 == 0o600
    assert b"existing-test-credential" not in result.stdout + result.stderr
    assert not list(tmp_path.glob("target.*"))
