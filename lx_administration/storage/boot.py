"""Read-only boot storage gate. Never creates storage, keys or recovery credentials."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

if __package__:
    from lx_administration.secret_storage import encrypted_storage, _require_encrypted_device
else:
    from secret_storage import encrypted_storage, _require_encrypted_device

BTRFS_SYSFS = Path("/sys/fs/btrfs")
BLOCK_SYSFS = Path("/sys/dev/block")


def probe(*args: str) -> dict:
    return json.loads(subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL))


def require_luks2(device: str) -> None:
    _require_encrypted_device(device)
    tree = probe("lsblk", "--json", "--paths", "--inverse", "--output", "NAME,TYPE", device)
    def visit(node):
        if node.get("type") == "crypt":
            status = subprocess.check_output(["cryptsetup", "status", node["name"]], text=True)
            if not any(line.split() == ["type:", "LUKS2"] for line in status.splitlines()):
                raise ValueError("Protected storage requires an actual LUKS2 mapping")
            return
        for child in node.get("children", []):
            visit(child)
    for node in tree["blockdevices"]:
        visit(node)


def verify_mount(path: str, expected: str, expected_type: str | None = None,
                 subvolume: str | None = None, *,
                 encrypted: bool = True) -> None:
    # Runtime callers retain encryption checks; only explicit install mode opts out.
    records = probe("findmnt", "--json", "--mountpoint", path,
                    "--output", "SOURCE,FSTYPE,UUID,FSROOT")["filesystems"]
    if len(records) != 1:
        raise ValueError(f"Missing or ambiguous required mount: {path}")
    fs = records[0]
    if expected_type is not None and fs["fstype"] != expected_type:
        raise ValueError(f"Unexpected filesystem type at {path}")
    if subvolume is not None and fs.get("fsroot") != "/" + subvolume.removeprefix("subvol=").lstrip("/"):
        raise ValueError(f"Unexpected Btrfs subvolume at {path}")
    if fs["fstype"] == "tmpfs" and expected_type == "tmpfs":
        encrypted_storage(Path(path), allow_runtime=True)
        return
    source = fs["source"].split("[", 1)[0]
    if not expected.startswith("/dev/"):
        # Bind sources are directories; resolve their filesystem independently.
        expected = probe("findmnt", "--json", "--target", expected,
                         "--output", "SOURCE")["filesystems"][0]["source"].split("[", 1)[0]
    if os.stat(source).st_rdev != os.stat(expected).st_rdev:
        raise ValueError(f"Unexpected backing device at {path}")
    if encrypted:
        encrypted_storage(Path(path))
        require_luks2(source)
    # lsblk on a Btrfs mount's SOURCE only covers one member. Check all members
    # from the kernel's mounted filesystem view; degraded/missing members fail.
    if fs["fstype"] == "btrfs":
        members = BTRFS_SYSFS / fs["uuid"] / "devices"
        devices = list(members.glob("*/dev"))
        if not devices:
            raise ValueError(f"No Btrfs members at {path}")
        for device in devices:
            number = device.read_text().strip()
            if number == "0:0":
                raise ValueError(f"Missing Btrfs member at {path}")
            if encrypted:
                require_luks2(f"/dev/block/{number}")


def reject_retired_mount(path: str) -> None:
    result = subprocess.run(["findmnt", "--mountpoint", path, "--noheadings"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 0:
        raise ValueError(f"Legacy container/bind still mounted at {path}; complete restore before activation")
    if result.returncode != 1:
        raise ValueError(f"Cannot inspect retired mount {path}")


def verify_key(path: str) -> None:
    key = Path(path)
    encrypted_storage(key)
    directory = key.parent.lstat()
    if directory.st_uid != 0 or directory.st_mode & 0o022:
        raise ValueError(f"Unsafe volume-key directory: {key.parent}")
    info = key.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077 or info.st_size < 32:
        raise ValueError(f"Missing or unsafe existing volume key: {path}; restore, never replace")


def key_device(device: str, mapping: str) -> tuple[str, int, int]:
    """Bind the evaluated raw device to the open mapping, including its LUKS UUID."""
    if (not device.startswith("/dev/") or ".." in Path(device).parts
            or not re.fullmatch(r"[A-Za-z0-9_.+-]+", mapping)):
        raise ValueError("Invalid secondary device or mapping specification")
    raw = os.stat(device)
    opened = os.stat(f"/dev/mapper/{mapping}")
    if not stat.S_ISBLK(raw.st_mode) or not stat.S_ISBLK(opened.st_mode):
        raise ValueError("Secondary storage must use block devices")
    identifier = str(uuid.UUID(subprocess.check_output(
        ["cryptsetup", "luksUUID", device], text=True,
        stderr=subprocess.DEVNULL, timeout=10).strip()))
    dm = BLOCK_SYSFS / f"{os.major(opened.st_rdev)}:{os.minor(opened.st_rdev)}"
    expected = f"CRYPT-LUKS2-{identifier.replace('-', '')}-{mapping}"
    if (dm / "dm/uuid").read_text().strip() != expected:
        raise ValueError(f"LUKS2 UUID does not match the open mapping: {mapping}")
    backing = [p.read_text().strip() for p in (dm / "slaves").glob("*/dev")]
    if backing != [f"{os.major(raw.st_rdev)}:{os.minor(raw.st_rdev)}"]:
        raise ValueError(f"Unexpected backing device for secondary mapping: {mapping}")
    return identifier, raw.st_rdev, opened.st_rdev


def verify_unlock(key: dict) -> None:
    """Test the existing keyslot without opening, closing or modifying a mapping."""
    verify_key(key["path"])
    try:
        identity = key_device(key["device"], key["mapping"])
        subprocess.run(
            ["cryptsetup", "open", "--type", "luks2", "--test-passphrase",
             "--batch-mode", "--key-file", key["path"], key["device"]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=True, timeout=30)
        if key_device(key["device"], key["mapping"]) != identity:
            raise ValueError("Secondary device changed during unlock verification")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Secondary key verification failed or timed out; restore the existing key before reboot") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--key", type=str)
    parser.add_argument("--mounted-storage", action="store_true",
                        help="Check running consumers' mounts and key permissions; not reboot readiness")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    try:
        if args.key:
            verify_key(args.key)
            return
        if args.spec is None:
            raise ValueError("Missing storage specification")
        spec = json.loads(args.spec.read_text())
        for path in spec.get("retiredMounts", []):
            reject_retired_mount(path)
        for path, expected in spec["mounts"].items():
            verify_mount(path, expected["device"], expected["fsType"], expected["subvolume"])
        for key in spec["keys"]:
            if args.mounted_storage:
                verify_key(key["path"])
            else:
                verify_unlock(key)
        for path in spec.get("paths", []) + args.paths:
            encrypted_storage(Path(path), allow_runtime=True)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Storage/recovery error: {exc}. See docs/boot-storage-migration.md.\n")


if __name__ == "__main__":
    main()
