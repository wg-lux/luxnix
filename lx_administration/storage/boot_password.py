"""Prompt once for a verified boot passphrase, retaining existing recovery slots."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import getpass
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import stat
import subprocess
import tempfile
import warnings

if __package__:
    from . import boot
    from .cutover import atomic_json
else:
    import boot
    from cutover import atomic_json

STATE = Path("/var/lib/luxnix-boot-passphrase")
MACHINE_ID = Path("/etc/machine-id")
KEY_FILE_BYTES = 64


def private(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (
        path.resolve() != path
        or not kind(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Boot-password state must be private and contain no symlinks")


@contextmanager
def key_fd(value: bytes):
    fd = os.memfd_create("luks-passphrase", os.MFD_CLOEXEC)
    try:
        with os.fdopen(os.dup(fd), "wb") as stream:
            stream.write(value)
        yield fd
    finally:
        os.close(fd)


def cryptsetup(*args: str, pass_fds=()) -> subprocess.CompletedProcess:
    # Passwords are anonymous-memory FDs only, never argv, environment or output.
    return subprocess.run(
        ["cryptsetup", *args],
        pass_fds=pass_fds,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=120,
        check=False,
    )


def accepts(device: str, password: bytes) -> bool:
    with key_fd(password) as fd:
        result = cryptsetup(
            "open",
            "--type",
            "luks2",
            "--test-passphrase",
            "--batch-mode",
            "--key-file",
            f"/proc/self/fd/{fd}",
            device,
            pass_fds=(fd,),
        )
    if result.returncode not in (0, 2):
        raise ValueError("Could not test the existing LUKS keyslots")
    return result.returncode == 0


def header_digest(device: str) -> str:
    result = cryptsetup("luksDump", "--dump-json-metadata", device)
    if result.returncode:
        raise ValueError("Could not inspect the LUKS2 header")
    metadata = json.loads(result.stdout)
    # Both binary/JSON headers plus the complete encrypted keyslot area.
    size = 2 * (4096 + int(metadata["config"]["json_size"]))
    size += int(metadata["config"]["keyslots_size"])
    if not 32768 <= size <= 128 * 1024 * 1024:
        raise ValueError(
            "Unsupported LUKS2 header extent; inspect before changing passwords"
        )
    digest = hashlib.sha256()
    with open(device, "rb", buffering=0) as stream:
        while size:
            block = stream.read(min(size, 1024 * 1024))
            if not block:
                raise ValueError("Incomplete LUKS2 header")
            digest.update(block)
            size -= len(block)
    return digest.hexdigest()


def secret(prompt: str) -> bytes:
    # getpass's fallback echoes input: reject it, including under redirected stdin.
    # getpass opens its own input FD. Buffered read/write text mode requires
    # seeking and fails on a real TTY with io.UnsupportedOperation.
    with open("/dev/tty", "w") as terminal, warnings.catch_warnings():
        if not terminal.isatty():
            raise ValueError("A private interactive terminal is required")
        warnings.simplefilter("error", getpass.GetPassWarning)
        value = getpass.getpass(prompt, stream=terminal).encode("utf-8")
    if not value or len(value) > 512 or b"\0" in value:
        raise ValueError("Enter a nonempty passphrase of at most 512 UTF-8 bytes")
    return value


def backup_header(device: str, state: Path, prefix: str) -> Path:
    """Write a private, durable LUKS header backup into its own new directory.

    It holds the keyslots valid now: anyone with it and a passphrase valid now can
    open the data, even after that passphrase is removed from the live header.
    """
    backup = Path(tempfile.mkdtemp(prefix=prefix, dir=state)) / "luks.header"
    if cryptsetup(
        "luksHeaderBackup", device, "--header-backup-file", str(backup)
    ).returncode:
        raise ValueError("LUKS header backup failed")
    os.chmod(backup, 0o600)
    with backup.open("rb") as stream:
        os.fsync(stream.fileno())
    for directory in (backup.parent, state):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return backup


def add_password(device: str, password: bytes, previous: bytes, state: Path) -> None:
    # A durable private header backup precedes the only header mutation. Never
    # remove existing slots, including the credential authorizing this addition.
    try:
        backup_header(device, state, "header-before-")
    except ValueError as error:
        raise ValueError(f"{error}; password was not changed") from error
    with key_fd(previous) as old_fd, key_fd(password) as new_fd:
        result = cryptsetup(
            "luksAddKey",
            "--batch-mode",
            "--key-file",
            f"/proc/self/fd/{old_fd}",
            device,
            f"/proc/self/fd/{new_fd}",
            pass_fds=(old_fd, new_fd),
        )
    if result.returncode:
        raise ValueError(
            "Could not add the passphrase; existing recovery slots were retained"
        )
    if not accepts(device, previous):
        raise ValueError("Recovery credential verification failed; do not reboot")


@contextmanager
def session(device: str):
    """Verified encrypted root, exclusive state lock and the current header identity."""
    # Check the complete executable contract before creating state or prompting.
    for command in ("findmnt", "lsblk", "swapon", "cryptsetup"):
        if shutil.which(command) is None:
            raise ValueError(f"Missing required executable: {command}")
    boot.verify_mount("/", "/dev/mapper/cryptroot")
    boot.encrypted_storage(STATE.parent)
    STATE.mkdir(mode=0o700, exist_ok=True)
    private(STATE, directory=True)
    boot.encrypted_storage(STATE)
    lock = os.open(STATE / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        private(STATE / ".lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity = boot.key_device(device, "cryptroot")
        machine = MACHINE_ID.read_text().strip()
        if len(machine) != 32 or any(c not in "0123456789abcdef" for c in machine):
            raise ValueError("Missing or invalid machine identity")
        expected = {
            "version": 1,
            "machine": machine,
            "uuid": identity[0],
            "header_sha256": header_digest(device),
        }
        yield identity, expected, STATE / "cryptroot.json"
    finally:
        os.close(lock)


def on_root_filesystem(path: Path) -> bool:
    return os.stat(path).st_dev == os.stat("/").st_dev


def enroll_key_file(device: str, path: Path) -> None:
    """Add a random key kept on removable media as one more root keyslot.

    The passphrase authorizes the addition and keeps working; no slot is removed.
    An existing key file is enrolled as it is and never rewritten.
    """
    with session(device) as (identity, expected, receipt):
        parent = path.parent
        if path.is_symlink() or parent.resolve() != parent or not parent.is_dir():
            raise ValueError("The key file path must be a plain file in a directory")
        if on_root_filesystem(parent):
            raise ValueError("The key file must be on the removable stick, not on root")
        passphrase = secret("Existing disk passphrase to authorize the USB key: ")
        if not accepts(device, passphrase):
            raise ValueError("Existing disk passphrase was rejected; nothing changed")
        if path.exists():
            key = path.read_bytes()
            if len(key) < 32:
                raise ValueError("The existing key file is too short; nothing changed")
        else:
            key = os.urandom(KEY_FILE_BYTES)
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400
            )
            with os.fdopen(fd, "wb") as stream:
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
        if (
            boot.key_device(device, "cryptroot") != identity
            or header_digest(device) != expected["header_sha256"]
        ):
            raise ValueError("Disk identity or keyslots changed during prompting; retry")
        if not accepts(device, key):
            add_password(device, key, passphrase, STATE)
            expected["header_sha256"] = header_digest(device)
        if not accepts(device, key) or not accepts(device, passphrase):
            raise ValueError("Key verification failed; do not reboot")
        # The header changed; the passphrase verified above stays the receipt's subject.
        atomic_json(receipt, expected)
        print("USB key enrolled and tested; the disk passphrase still unlocks root.")


def prepare(device: str, *, change: bool = False) -> None:
    with session(device) as (identity, expected, receipt):
        if receipt.exists() or receipt.is_symlink():
            private(receipt)
            if not change and json.loads(receipt.read_text()) == expected:
                return
        password = secret("Boot disk passphrase (new only with --change): ")
        if secret("Confirm boot disk passphrase: ") != password:
            raise ValueError("Passphrases do not match; nothing changed")
        enrolled = accepts(device, password)
        previous = None
        if not enrolled:
            if not change:
                raise ValueError("Existing disk passphrase rejected; adding a credential requires explicit --change")
            if len(password.decode("utf-8")) < 12:
                raise ValueError(
                    "A new disk passphrase must contain at least 12 characters"
                )
            previous = secret(
                "Existing disk/recovery passphrase to authorize adding it: "
            )
            if not accepts(device, previous):
                raise ValueError("Existing credential was rejected; nothing changed")
        if (
            boot.key_device(device, "cryptroot") != identity
            or header_digest(device) != expected["header_sha256"]
        ):
            raise ValueError(
                "Disk identity or keyslots changed during prompting; retry"
            )
        if previous is not None:
            add_password(device, password, previous, STATE)
            expected["header_sha256"] = header_digest(device)
        if not accepts(device, password):
            raise ValueError("Boot passphrase verification failed; do not reboot")
        if (
            boot.key_device(device, "cryptroot") != identity
            or header_digest(device) != expected["header_sha256"]
        ):
            raise ValueError(
                "Disk identity or keyslots changed during verification; retry"
            )
        pending = receipt.with_name(receipt.name + ".pending")
        if pending.exists() or pending.is_symlink():
            private(pending)
        atomic_json(receipt, expected)
        print("Boot passphrase verified; existing recovery credentials retained.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True)
    parser.add_argument(
        "--change",
        action="store_true",
        help="Prompt again to verify or add an operator-chosen passphrase",
    )
    parser.add_argument(
        "--enroll-key-file",
        type=Path,
        metavar="PATH",
        help="Create or reuse a key file on mounted removable media and add it",
    )
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError("Run as root on the machine being rebuilt")
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
        if args.enroll_key_file is not None:
            if args.change:
                raise ValueError("--change and --enroll-key-file are separate steps")
            enroll_key_file(args.device, args.enroll_key_file)
        else:
            prepare(args.device, change=args.change)
    except (
        OSError,
        ValueError,
        KeyError,
        EOFError,
        KeyboardInterrupt,
        getpass.GetPassWarning,
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
    ) as exc:
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        if isinstance(exc, FileNotFoundError) and exc.filename:
            # Paths identify the missing dependency; never include subprocess output.
            detail = f"Missing file or executable: {exc.filename}"
        parser.exit(
            1,
            "Boot-password setup failed: " + detail + ".\n"
            "No existing keyslots were removed. Do not reboot until staging succeeds.\n"
            "Open Konsole on this host, log in on Ctrl+Alt+F3, or connect with "
            "ssh -t admin@HOST (replace HOST with this machine).\n"
            "Use a session you control without terminal recording or screen sharing; "
            "password input is hidden. Run tty: it should print "
            "/dev/pts/N or /dev/ttyN.\n"
            "From your updated LuxNix checkout on this host, run:\n"
            '  nix build ".#nixosConfigurations.$(hostname)'
            '.config.system.build.toplevel" '
            "--out-link result-boot --accept-flake-config\n"
            "  sudo ./result-boot/sw/bin/luxnix-setup-boot-password\n"
            '  sudo nixos-rebuild boot --flake ".#$(hostname)" --accept-flake-config\n'
            "Enter the existing disk password and confirmation; explicit --change also needs "
            "the existing disk/recovery password. Never put passwords in commands.\n"
            "See docs/boot-storage-migration.md (Password setup during rebuild).\n",
        )


if __name__ == "__main__":
    main()
