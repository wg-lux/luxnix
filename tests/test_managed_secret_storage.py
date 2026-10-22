"""Exercise the shared storage verifier without inspecting live host secrets."""

import json
from pathlib import Path
import subprocess

import pytest

from lx_administration import secret_storage as storage

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules/nixos/roles/managed-secrets/default.nix"


@pytest.mark.parametrize(
    "filesystem,devices,allow_runtime,success",
    [
        ("ext4", [{"type": "crypt"}], False, True),
        ("btrfs", [{"type": "lvm", "children": [{"type": "crypt"}]}], False, True),
        (
            "ext4",
            [{"type": "raid", "children": [{"type": "crypt"}, {"type": "disk"}]}],
            False,
            False,
        ),
        ("ext4", [{"type": "disk"}], False, False),
        ("ext4", [], False, False),
        ("tmpfs", [], True, True),
        ("tmpfs", [], False, False),
        ("overlay", [], True, False),
        ("ramfs", [], True, False),
    ],
)
def test_storage_boundary(
    tmp_path, monkeypatch, filesystem, devices, allow_runtime, success
):
    def probe(command, **kwargs):
        return json.dumps(
            {
                "swapon": {"swapdevices": []},
                "findmnt": {
                    "filesystems": [
                        {"fstype": filesystem, "source": "/dev/mapper/test[/secrets]"}
                    ]
                },
                "lsblk": {"blockdevices": devices},
            }[command[0]]
        ).encode()

    monkeypatch.setattr(storage.subprocess, "check_output", probe)
    destination = tmp_path / "not-created" / "secret"
    if success:
        storage.encrypted_storage(destination, allow_runtime=allow_runtime)
    else:
        with pytest.raises(ValueError):
            storage.encrypted_storage(destination, allow_runtime=allow_runtime)
    assert not destination.parent.exists()


@pytest.mark.parametrize(
    "response", [{"swapdevices": [{"name": "/swapfile"}]}, {}, None]
)
def test_swap_or_invalid_probe_fails_closed(tmp_path, monkeypatch, response):
    monkeypatch.setattr(
        storage.subprocess, "check_output", lambda *a, **k: json.dumps(response)
    )
    with pytest.raises(ValueError):
        storage.encrypted_storage(tmp_path / "secret", allow_runtime=True)


def test_failed_probe_fails_closed(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "swapon")

    monkeypatch.setattr(storage.subprocess, "check_output", fail)
    with pytest.raises(subprocess.CalledProcessError):
        storage.encrypted_storage(tmp_path / "secret")


def test_storage_rejects_symlink_before_probing(tmp_path, monkeypatch):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "link"
    link.symlink_to(actual, target_is_directory=True)

    def unexpected_probe(*args, **kwargs):
        pytest.fail("symlink validation must precede probes")

    monkeypatch.setattr(storage.subprocess, "check_output", unexpected_probe)
    with pytest.raises(ValueError, match="without symlinks"):
        storage.encrypted_storage(link / "secret")
    assert not (actual / "secret").exists()


def test_secret_creation_guards_before_write_and_disallows_offline_fallback():
    source = MODULE.read_text()
    generator = source.split("  mkSecretScript =", 1)[1].split(
        "  # Main secret generation script", 1
    )[0]
    assert generator.index('${verifySecretStorage} "$SECRET_FILE"') < generator.index(
        'mkdir -p "$SECRET_DIR"'
    )
    assert "allowOffline" not in source
    assert "continuing with the existing local secret" not in source
    assert "LimitCORE = 0;" in source


def test_failed_refresh_preserves_file_but_fails_authentication(tmp_path):
    import re

    destination = tmp_path / "synthetic-secret"
    destination.write_text("synthetic-old-generation")
    source = MODULE.read_text()
    script = source.split('pkgs.writeShellScript "generate-${name}"', 1)[1]
    script = script.split("''\n", 1)[1].split("\n    '';", 1)[0]
    script = re.sub(
        r'SHOULD_REFRESH="\$\{.*?\}"', 'SHOULD_REFRESH="true"', script, flags=re.DOTALL
    )
    script = re.sub(
        r"\$\{\s*if secretConfig.customScript.*?\n          \}",
        "false",
        script,
        flags=re.DOTALL,
    )
    for key, value in {
        "secretConfig.path": str(destination),
        "verifySecretStorage": "true",
        "name": "synthetic",
        "secretConfig.description": "synthetic",
        "secretConfig.owner": "root",
        "secretConfig.group": "root",
        "secretConfig.permissions": "0600",
    }.items():
        script = script.replace("${" + key + "}", value)
    assert "${" not in script
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "Failed to generate or refresh" in result.stderr
    assert destination.read_text() == "synthetic-old-generation"
    assert not list(tmp_path.glob(".synthetic.tmp.*"))
