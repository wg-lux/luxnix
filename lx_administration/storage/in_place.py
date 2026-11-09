"""Encrypt an existing Btrfs root partition in place with LUKS2, keeping its data.

Runs from trusted installer media with the target unmounted. The filesystem keeps
its identity and contents. Data in existing containers is copied to its normal paths
on the now encrypted root and compared; the containers are only ever opened read-only
and stay until retired separately after acceptance. Nothing here formats a data
partition. The only erased area is a plaintext swap partition, which holds no durable
data and may hold secrets.

An interrupted conversion is resumed from the LUKS2 header, never restarted.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from lx_administration.storage import boot_password
from lx_administration.storage.cutover import atomic_json

# Twice the default LUKS2 header size, as cryptsetup recommends for encrypting.
HEADER_RESERVE = "32M"
MIN_PASSPHRASE_LENGTH = 12
# Unaffected by the US/German layout difference; other characters can differ between
# the boot prompt, which uses the kernel default layout, and a desktop terminal.
SPACE_MARGIN = 1024**3
# Separate from boot_password.STATE, which must stay private and exactly as it expects.
CONSOLIDATION_STATE = Path("/var/lib/luxnix-in-place")
LAYOUT_SAFE = re.compile(r"[a-xA-X0-9 ]+")
PLAINTEXT, ENCRYPTING, ENCRYPTED = "plaintext", "encrypting", "encrypted"
_operation_locks: ContextVar[tuple[int, ...]] = ContextVar(
    "operation_locks", default=()
)


class InPlaceError(ValueError):
    pass


@contextmanager
def operation_locks(*fds: int):
    """Keep orchestration locks alive in children after controller termination."""
    token = _operation_locks.set(tuple(dict.fromkeys((*_operation_locks.get(), *fds))))
    try:
        yield
    finally:
        _operation_locks.reset(token)


def run(*args: str, pass_fds=(), timeout: int | None = 600) -> str:
    # Never relay diagnostics; they can name private paths.
    result = subprocess.run(
        args,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        pass_fds=tuple(dict.fromkeys((*pass_fds, *_operation_locks.get()))),
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise InPlaceError(
            f"{Path(args[0]).name} {args[1] if len(args) > 1 else ''} failed "
            f"(exit {result.returncode}); the target may be partially modified. "
            "Preserve the journal and inspect/resume from trusted installer media; "
            "never format to retry"
        )
    return result.stdout.strip()


def with_key(
    passphrase: bytes, action: str, *arguments: str, timeout: int | None = 600
) -> str:
    """Run cryptsetup with the passphrase on a private descriptor, never in argv."""
    with boot_password.key_fd(passphrase) as fd:
        return run(
            "cryptsetup",
            action,
            "--key-file",
            f"/proc/self/fd/{fd}",
            *arguments,
            pass_fds=(fd,),
            timeout=timeout,
        )


def check_passphrase(value: bytes) -> None:
    """Refuse a passphrase that could differ when typed at the boot prompt."""
    text = value.decode("utf-8", errors="replace")
    if len(value) < MIN_PASSPHRASE_LENGTH:
        raise InPlaceError(
            f"The root passphrase needs at least {MIN_PASSPHRASE_LENGTH} characters"
        )
    if not LAYOUT_SAFE.fullmatch(text):
        raise InPlaceError(
            "Use only letters a-x, digits and spaces. Other characters, including y "
            "and z, can differ at the boot prompt and would lock you out"
        )


def root_state(device: str) -> str:
    """Classify the partition from its own metadata; nothing else is trusted."""
    kind = run("blkid", "-p", "-o", "value", "-s", "TYPE", device)
    if kind == "btrfs":
        return PLAINTEXT
    if kind != "crypto_LUKS":
        raise InPlaceError(
            "The root partition is neither plaintext Btrfs nor LUKS; stop and inspect"
        )
    metadata = json.loads(run("cryptsetup", "luksDump", "--dump-json-metadata", device))
    required = metadata.get("config", {}).get("requirements", {}).get("mandatory", [])
    return ENCRYPTING if any("reencrypt" in r for r in required) else ENCRYPTED


def filesystem_uuid(device: str) -> str:
    return run("blkid", "-p", "-o", "value", "-s", "UUID", device)


@contextmanager
def mounted(device: str, *options: str):
    directory = tempfile.mkdtemp(prefix="luxnix-in-place-", dir="/run")
    run("mount", "-o", ",".join(options), device, directory)
    try:
        yield Path(directory)
    finally:
        run("umount", directory)
        os.rmdir(directory)


def subvolume_path(mounts: dict, path: str) -> str:
    """Translate a target path to its location below the Btrfs top level."""
    owner = max(
        (m for m in mounts if m == "/" or path == m or path.startswith(m + "/")),
        key=len,
    )
    option = next(
        (o for o in mounts[owner]["options"] if o.startswith("subvol=")), "subvol=/"
    )
    relative = path if owner == "/" else path[len(owner) :]
    return option.removeprefix("subvol=").strip("/") + relative


@contextmanager
def opened_container(path: Path, container: dict, passphrase: bytes):
    """Open a container read-only; this workflow never writes to one."""
    name = f"luxnix-consolidate-{container['name']}"
    with_key(passphrase, "open", "--type", "luks2", "--readonly", str(path), name)
    try:
        with mounted(f"/dev/mapper/{name}", "ro") as point:
            yield point
    finally:
        run("cryptsetup", "close", name)


def free_bytes(top: Path) -> int:
    usage = run("btrfs", "filesystem", "usage", "-b", str(top))
    match = re.search(r"Free \(estimated\):\s+(\d+)", usage)
    if not match:
        raise InPlaceError("Could not determine free space on the root filesystem")
    return int(match.group(1))


def bind_sources(container: dict, binds: dict) -> dict:
    return {t: b for t, b in binds.items() if b["volume"] == container["name"]}


def verify_containers_before_change(
    device: str,
    mounts: dict,
    containers: list[dict],
    binds: dict,
    passphrases: dict[str, bytes],
) -> None:
    """Prove the data can be opened and fits, while the disk is still untouched."""
    needed = 0
    with mounted(device, "ro", "subvolid=5") as top:
        for container in containers:
            path = top / subvolume_path(mounts, container["container"])
            if not path.is_file():
                raise InPlaceError(f"Missing container: {container['container']}")
            if not boot_password.accepts(str(path), passphrases[container["name"]]):
                raise InPlaceError(
                    f"That passphrase does not open {container['name']}. Nothing has "
                    "been changed. Its data cannot be reached without it"
                )
            with opened_container(
                path, container, passphrases[container["name"]]
            ) as point:
                for target, bind in bind_sources(container, binds).items():
                    source = point / bind["directory"]
                    if not source.is_dir():
                        raise InPlaceError(
                            f"{container['name']} has no {bind['directory']} for "
                            f"{target}; its layout does not match the configuration"
                        )
                    needed += int(run("du", "-sb", str(source)).split()[0])
        if free_bytes(top) < needed + SPACE_MARGIN:
            raise InPlaceError(
                "The root filesystem lacks the free space to hold the container data "
                "while the old containers still exist. Nothing has been changed"
            )


def shrink_filesystem(device: str) -> None:
    """Make room for the LUKS2 header. Btrfs only resizes while mounted."""
    run("btrfs", "check", "--readonly", device, timeout=7200)
    with mounted(device, "subvolid=5") as top:
        run(
            "btrfs",
            "filesystem",
            "resize",
            f"-{HEADER_RESERVE}",
            str(top),
            timeout=7200,
        )
        run("sync")


def encrypt(device: str, passphrase: bytes, *, resume: bool) -> None:
    """Start or resume. After a crash LUKS2 requires repair before it will resume."""
    arguments = (
        ["--resume-only"]
        if resume
        else [
            "--encrypt",
            "--type",
            "luks2",
            "--reduce-device-size",
            HEADER_RESERVE,
            "--batch-mode",
        ]
    )
    if resume:
        with_key(passphrase, "repair", "--batch-mode", device, timeout=None)
    with_key(passphrase, "reencrypt", *arguments, device, timeout=None)


def open_root(device: str, passphrase: bytes) -> None:
    with_key(passphrase, "open", "--type", "luks2", device, "cryptroot")


def erase_plaintext_swap(partitions: list[str]) -> tuple[list[str], list[str]]:
    """Swap can hold secrets in clear; erasing it loses nothing durable.

    Root is already encrypted here, so a failure is reported for the operator to finish
    rather than ending the conversion. blkid exits 2 when a partition has no signature.
    """
    erased, unchecked = [], []
    for partition in partitions:
        probe = subprocess.run(
            ["blkid", "-p", "-o", "value", "-s", "TYPE", partition],
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode not in {0, 2}:
            unchecked.append(partition)
        elif probe.stdout.strip() == "swap":
            try:
                run("blkdiscard", "--force", "--zeroout", partition, timeout=7200)
                erased.append(partition)
            except (InPlaceError, subprocess.SubprocessError):
                unchecked.append(partition)
    return erased, unchecked


def mount_target(mounts: dict, root: Path) -> None:
    """Mount the evaluated Btrfs graph and EFI at the install root."""
    for mount in sorted(mounts, key=lambda m: m.count("/") if m != "/" else 0):
        entry = mounts[mount]
        if entry["fsType"] in {"none", "tmpfs"}:
            continue
        target = root / mount.lstrip("/") if mount != "/" else root
        target.mkdir(parents=True, exist_ok=True)
        options = [o for o in entry["options"] if not o.startswith("x-systemd")]
        options = [o for o in options if o not in {"nofail", "noauto"}]
        command = ["mount", "-t", entry["fsType"]]
        if options:
            command += ["-o", ",".join(options)]
        run(*command, entry["device"], str(target))


def consolidate_target(source: Path, destination: Path, marker: Path) -> None:
    """Copy, compare, then publish, so an interruption never leaves half a directory."""
    staging = destination.with_name(destination.name + ".consolidating")
    aside = destination.with_name(destination.name + ".pre-consolidation")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if staging.exists():
        run("rm", "-rf", "--one-file-system", str(staging))
    if destination.exists() and any(destination.iterdir()) and aside.exists():
        raise InPlaceError(f"{aside} already exists; inspect it, do not overwrite")
    run("cp", "-a", "--preserve=all", str(source), str(staging), timeout=None)
    run("diff", "-r", "--no-dereference", str(source), str(staging), timeout=None)
    run("sync")
    if destination.is_dir() and not any(destination.iterdir()):
        destination.rmdir()
    elif destination.exists():
        # Whatever the old root held under this mount point; never silently lost.
        os.rename(destination, aside)
    os.rename(staging, destination)
    marker.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker.write_text("consolidated\n")
    run("sync")


def consolidate_containers(
    containers: list[dict], binds: dict, passphrases: dict[str, bytes], root: Path
) -> list[str]:
    """Move container data to its normal paths on the encrypted root.

    Containers are opened read-only and left in place: removing them is a separate
    step after acceptance. Targets publish parents first across every container,
    because a nested target can come from a different container than its parent.
    """
    state = root / CONSOLIDATION_STATE.relative_to("/")
    by_name = {c["name"]: c for c in containers}
    done = []
    for target in sorted(binds, key=lambda t: t.count("/")):
        bind = binds[target]
        container = by_name[bind["volume"]]
        marker = state / target.strip("/").replace("/", "__")
        done.append(target)
        if marker.exists():
            continue
        path = root / container["container"].lstrip("/")
        with opened_container(path, container, passphrases[container["name"]]) as point:
            consolidate_target(
                point / bind["directory"], root / target.lstrip("/"), marker
            )
    return done


def retire_containers(containers: list[dict], binds: dict) -> list[str]:
    """Delete container files once their data lives on the encrypted root."""
    for container in containers:
        path = Path(container["container"])
        if run("losetup", "--noheadings", "-j", str(path)):
            raise InPlaceError(f"{path} is still attached; close it first")
        for target in bind_sources(container, binds):
            marker = CONSOLIDATION_STATE / target.strip("/").replace("/", "__")
            content = Path(target)
            if not marker.exists() or not content.is_dir() or os.path.ismount(content):
                raise InPlaceError(
                    f"{target} was not consolidated onto the encrypted root; "
                    f"keeping {path}"
                )
    removed = []
    for container in containers:
        path = Path(container["container"])
        if path.exists():
            path.unlink()
            removed.append(str(path))
    run("sync")
    return removed


def write_boot_receipt(device: str, passphrase: bytes, root: Path) -> None:
    """Record that this passphrase opens this header, for the installed verifier."""
    if not boot_password.accepts(device, passphrase):
        raise InPlaceError("The root passphrase no longer opens the converted disk")
    state = root / boot_password.STATE.relative_to("/")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    machine = (root / "etc/machine-id").read_text().strip()
    atomic_json(
        state / "cryptroot.json",
        {
            "version": 1,
            "machine": machine,
            "uuid": run("cryptsetup", "luksUUID", device),
            "header_sha256": boot_password.header_digest(device),
        },
    )


def convert(
    layout: dict,
    mounts: dict,
    *,
    root_passphrase: bytes,
    container_passphrases: dict[str, bytes],
    root: Path = Path("/mnt"),
) -> dict:
    """Run or resume the conversion and leave the encrypted target mounted at root."""
    device = layout["root_device"]
    state = root_state(device)
    containers = layout["containers"]
    original = None
    if state == PLAINTEXT:
        check_passphrase(root_passphrase)
        original = filesystem_uuid(device)
        verify_containers_before_change(
            device, mounts, containers, layout["binds"], container_passphrases
        )
        shrink_filesystem(device)
        encrypt(device, root_passphrase, resume=False)
    elif state == ENCRYPTING:
        encrypt(device, root_passphrase, resume=True)
    if root_state(device) != ENCRYPTED:
        raise InPlaceError("Encryption did not complete; rerun to resume it")
    open_root(device, root_passphrase)
    converted = filesystem_uuid("/dev/mapper/cryptroot")
    if original is not None and converted != original:
        raise InPlaceError("The filesystem identity changed during encryption; stop")
    run("btrfs", "check", "--readonly", "/dev/mapper/cryptroot", timeout=7200)
    erased, unchecked = erase_plaintext_swap(layout["swap_partitions"])
    mount_target(mounts, root)
    consolidated = consolidate_containers(
        containers, layout["binds"], container_passphrases, root
    )
    write_boot_receipt(device, root_passphrase, root)
    return {
        "filesystem_uuid": converted,
        "consolidated": consolidated,
        "swap_erased": erased,
        "swap_unchecked": unchecked,
    }
