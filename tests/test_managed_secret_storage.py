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
        if command[0] == "swapon":
            return ""
        return json.dumps(
            {
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
    "sources,device_type,success",
    [
        (["/dev/mapper/test[/replica]"] * 2, "crypt", True),
        (["/dev/plain[/replica]"] * 2, "part", False),
        (["/dev/mapper/test[/replica]", "/dev/plain"], "crypt", False),
        (["/dev/plain", "/dev/mapper/test[/replica]"], "crypt", False),
        (["/dev/mapper/test[/replica]", "/dev/mapper/test[/other]"], "crypt", False),
    ],
)
def test_stacked_mounts_require_identical_encrypted_sources(
    tmp_path, monkeypatch, sources, device_type, success
):
    def probe(command, **kwargs):
        if command[0] == "swapon":
            return ""
        return json.dumps(
            {
                "findmnt": {
                    "filesystems": [
                        {"fstype": "ext4", "source": source} for source in sources
                    ]
                },
                "lsblk": {"blockdevices": [{"type": device_type}]},
            }[command[0]]
        )

    monkeypatch.setattr(storage.subprocess, "check_output", probe)
    if success:
        storage.encrypted_storage(tmp_path)
    else:
        with pytest.raises(ValueError):
            storage.encrypted_storage(tmp_path)


@pytest.mark.parametrize(
    "second", [{"source": "/dev/mapper/test", "fstype": "tmpfs"}, None]
)
def test_stacked_mounts_reject_conflicting_types_or_malformed_entries(
    monkeypatch, second
):
    monkeypatch.setattr(
        storage,
        "_probe",
        lambda *args: {
            "filesystems": [{"source": "/dev/mapper/test", "fstype": "ext4"}, second]
        },
    )
    with pytest.raises(ValueError):
        storage._mounted_filesystem(Path("/secrets"))


def _swap_probe(swaps, devices, filesystem_source="/dev/mapper/test[/swap]"):
    def probe(command, **kwargs):
        if command[0] == "swapon":
            return swaps
        return json.dumps(
            {
                "findmnt": {
                    "filesystems": [{"fstype": "btrfs", "source": filesystem_source}]
                },
                "lsblk": {"blockdevices": devices},
            }[command[0]]
        )

    return probe


@pytest.mark.parametrize(
    "swaps,devices,backing,success",
    [
        ("", [], None, True),
        ("/dev/zram0 partition\n", [], "none", True),
        ("/dev/zram0 partition\n", [], None, True),
        ("/dev/zram0 partition\n", [], "/dev/sda2", False),
        ("/swap/swapfile file\n", [{"type": "crypt"}], None, True),
        ("/dev/mapper/swap partition\n", [{"type": "crypt"}], None, True),
        ("/swap/swapfile file\n", [{"type": "disk"}], None, False),
        ("/dev/sda2 partition\n", [{"type": "part"}], None, False),
        (
            "/dev/zram0 partition\n/dev/sda2 partition\n",
            [{"type": "part"}],
            "none",
            False,
        ),
        ('{"swapdevices": [{"name": "/swapfile"}]}', [], None, False),
        ("{}", [], None, False),
        ("/swap/swapfile\n", [{"type": "crypt"}], None, False),
    ],
)
def test_swap_must_not_reach_plaintext_storage(
    tmp_path, monkeypatch, swaps, devices, backing, success
):
    sys_block = tmp_path / "sys-block"
    if backing is not None:
        (sys_block / "zram0").mkdir(parents=True)
        (sys_block / "zram0" / "backing_dev").write_text(backing + "\n")
    monkeypatch.setattr(storage, "SYS_BLOCK", sys_block)
    monkeypatch.setattr(storage.subprocess, "check_output", _swap_probe(swaps, devices))
    if success:
        storage._require_protected_swap()
    else:
        with pytest.raises(ValueError):
            storage._require_protected_swap()


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
