"""Prepare operator-owned encrypted containers and migrate before writers start.

Never format an existing file, overwrite a populated destination, or remove a
source. The JSON contract contains paths only; passphrases never enter it.
"""
from __future__ import annotations

import argparse
import configparser
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
import runpy

if __package__:
    from . import cutover as staged_copy
else:
    import cutover as staged_copy


PASSPHRASE_ATTEMPTS = 5
PASSPHRASE_KEYNAME = "luxnix-operator-storage"


class MigrationError(RuntimeError):
    pass


def require_secure_boot():
    variable = Path('/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c')
    if not variable.is_file() or variable.read_bytes()[4:] != b'\x01':
        raise MigrationError('TPM unlock requires enabled UEFI Secure Boot; enroll trusted boot first')


def run(*args, input=None, pass_fds=()):
    result = subprocess.run(args, input=input, pass_fds=pass_fds, capture_output=True, check=False)
    if result.returncode:
        # rsync and cryptsetup diagnostics can contain private filenames.
        raise MigrationError(f"{args[0]} failed (exit {result.returncode}); sources retained")
    return result.stdout


def plain_path(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or path.resolve() != path:
        raise MigrationError("Storage paths must be absolute and contain no symlinks")
    return path


atomic_json = staged_copy.atomic_json

class Migration:
    def __init__(self, config, verifier):
        self.config = config
        self.verifier = verifier

    def unlock(self, name):
        volume = self.config["volumes"][name]
        container = plain_path(volume["container"])
        mapping = volume["device"].removeprefix("/dev/mapper/")
        if volume.get("luksUUID") and run("cryptsetup", "luksUUID", str(container)).decode().strip() != volume["luksUUID"]:
            raise MigrationError("Native LUKS UUID does not match the declared volume")
        if Path(volume["device"]).exists():
            status = run("cryptsetup", "status", mapping).decode()
            fields = dict(line.strip().split(":", 1) for line in status.splitlines() if ":" in line)
            if fields.get("loop", "").strip() != str(container):
                raise MigrationError("Open mapping has a different backing container")
            return
        self.verifier._require_protected_swap()
        if self.config.get("unlockMethod") == "local-openbao":
            if not volume.get("luksUUID") or not container.is_file():
                raise MigrationError("Local OpenBao requires an existing UUID-bound container")
            client = runpy.run_path(self.config["openbaoClient"])
            credentials = Path(os.environ["CREDENTIALS_DIRECTORY"])
            key = client["volume_key"](
                self.config["machine"], name, volume["luksUUID"], credentials / "volume.unlock"
            )
            run("cryptsetup", "open", "--type", "luks", "--key-file=-", str(container), mapping, input=key)
            return
        if self.config.get("unlockMethod", "passphrase") == "tpm2":
            require_secure_boot()
            if not container.is_file():
                raise MigrationError("TPM storage must be provisioned and enrolled before automatic startup")
            metadata = json.loads(run("cryptsetup", "luksDump", "--dump-json-metadata", str(container)))
            tokens = {key: token for key, token in metadata.get("tokens", {}).items()
                      if token.get("type") == "systemd-tpm2"}
            unattended = [key for key, token in tokens.items() if not token.get("tpm2-pin", False)]
            if not unattended or any(7 not in token.get("tpm2-pcrs", []) for token in tokens.values()):
                raise MigrationError("No unattended Secure Boot-bound TPM enrollment; enroll this container first")
            run("cryptsetup", "open", "--type", "luks", "--token-only", "--token-type", "systemd-tpm2",
                "--token-id", unattended[0], "--external-tokens-path", self.config["tpm2PluginPath"],
                str(container), mapping)
            return
        if not container.is_file():
            raise MigrationError("Container missing; startup never provisions or formats storage")
        run("cryptsetup", "isLuks", str(container))
        if volume.get("keyFile"):
            self.unlock_with_key_file(volume["keyFile"], container, mapping)
            return
        # The boot prompt caches the answer in the kernel keyring, so containers
        # sharing one passphrase ask once; a wrong or stale answer asks again.
        for attempt in range(PASSPHRASE_ATTEMPTS):
            ask = ["systemd-ask-password", "--timeout=0", f"--keyname={PASSPHRASE_KEYNAME}"]
            if attempt == 0:
                ask.append("--accept-cached")
            key = run(*ask, f"Unlock {mapping}:").rstrip(b"\n")
            try:
                run("cryptsetup", "open", "--type", "luks", "--key-file=-", str(container), mapping, input=key)
                return
            except MigrationError:
                continue
        raise MigrationError(f"No valid passphrase for {mapping} after {PASSPHRASE_ATTEMPTS} attempts")

    @staticmethod
    def unlock_with_key_file(key_file, container, mapping):
        """Open with the key sops-nix installed after the secrets volume opened.

        Never falls back to a prompt: a missing or rejected key is reported and
        the recovery passphrase stays available through luxnix-operator-storage.
        """
        recovery = f"recover with: sudo luxnix-operator-storage open {mapping}"
        path = Path(key_file)
        # sops-nix publishes secrets as symlinks into its runtime generation.
        if not path.is_absolute() or not path.exists() or not private_source(path.resolve()):
            raise MigrationError(f"Automatic unlock key for {mapping} is missing or not private; {recovery}")
        try:
            run("cryptsetup", "open", "--type", "luks", f"--key-file={path.resolve()}", str(container), mapping)
        except MigrationError as exc:
            raise MigrationError(f"Automatic unlock key for {mapping} was rejected; {recovery}") from exc

    def provision(self, name, record):
        """Explicit operation only, after the controller has verified both escrows."""
        configured_method = self.config.get("unlockMethod", "passphrase")
        method = record.get("backend", configured_method)
        if method != "passphrase":
            raise MigrationError(
                "Alternative container enrollment is retired; use boot LUKS2"
            )
        if method == "passphrase" and configured_method != "passphrase":
            raise MigrationError(
                "Passphrase provisioning requires the configured passphrase unlock policy"
            )
        volume = self.config["volumes"][name]
        container = plain_path(volume["container"])
        expected_uuid = str(uuid.UUID(record["luks_uuid"]))
        if volume.get("luksUUID") not in (None, expected_uuid):
            raise MigrationError("Provision request does not match the declared native LUKS UUID")
        if (record["machine_id"] != Path("/etc/machine-id").read_text().strip()
                or record["volume"] != name or not record.get("primary_escrow")
                or not record.get("emergency_export")):
            raise MigrationError("Provisioning identity or recovery custody does not match")
        key = record["recovery_passphrase"].encode("ascii")
        if len(key) != 64 or any(c not in b"0123456789abcdef" for c in key):
            raise MigrationError("Provisioning requires a random 256-bit recovery passphrase")
        if (record.get("host") != self.config["machine"]
                or record.get("container") != str(container)):
            raise MigrationError(
                "Provision request does not match the declared host and container"
            )
        self.verifier._require_protected_swap()
        self.provision_container(name, record, key, expected_uuid)

    def allocate(self, name, container=None):
        volume = self.config["volumes"][name]
        container = plain_path(volume["container"]) if container is None else container
        sources = [plain_path(path) for path, bind in self.config["binds"].items()
                   if bind["volume"] == name and Path(path).exists()]
        used = sum(int(run("du", "-sx", "--block-size=1", str(path)).split()[0]) for path in sources)
        size = max(volume["minimumSizeMiB"] * 1024**2, used * 2 + 256 * 1024**2)
        if shutil.disk_usage(container.parent).free < size + 256 * 1024**2:
            raise MigrationError("Insufficient space for encrypted storage and safety reserve")
        fd = os.open(container, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.posix_fallocate(fd, 0, size)
            os.fsync(fd)
        finally:
            os.close(fd)

    def provision_container(self, name, record, recovery, expected_uuid, *, openbao=None):
        """Resume only authenticated LUKS state; never reformat an existing file."""
        volume = self.config["volumes"][name]
        container = plain_path(volume["container"])
        marker = container.with_suffix(container.suffix + ".provisioned.json")
        pending = container.with_suffix(container.suffix + ".provisioning.json")
        identity = {"machine_id": record["machine_id"], "volume": name, "luks_uuid": expected_uuid}
        if record.get("origin") != "new" or volume.get("fsType", "ext4") != "ext4":
            raise MigrationError("New-container provisioning requires new-volume escrow and ext4; adopt existing volumes")
        if marker.exists() and json.loads(marker.read_text()) != identity:
            raise MigrationError("Conflicting completed provisioning receipt")
        if pending.exists() and json.loads(pending.read_text()) != identity:
            raise MigrationError("Conflicting in-progress provisioning receipt")
        if container.exists() and not marker.exists() and not pending.exists():
            raise MigrationError(
                "Existing container has no matching provisioning receipt; never reformat it"
            )
        if openbao is not None:
            # Authenticate and persist the independent key before allocation.
            openbao.volume_record(name, expected_uuid, record["provisioner"],
                                  str(container) if container.exists() else None)
        if container.exists():
            if run("cryptsetup", "luksUUID", str(container)).decode().strip() != expected_uuid:
                raise MigrationError("Existing container UUID differs; never reformat it")
            run("cryptsetup", "open", "--test-passphrase", "--key-file=-", str(container), input=recovery)
        else:
            if marker.exists() or Path(volume["device"]).exists():
                raise MigrationError("Missing container has existing provisioning state; inspect before proceeding")
            temporary = plain_path(str(container) + ".allocating")
            if temporary.exists() and not pending.exists():
                raise MigrationError("Unowned allocation file; refusing replacement")
            if not pending.exists():
                atomic_json(pending, identity)
            if temporary.exists():
                info = temporary.stat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                    raise MigrationError("Unsafe allocation file")
                probe = subprocess.run(["cryptsetup", "isLuks", str(temporary)], capture_output=True, check=False)
                if probe.returncode == 1:
                    # This unpublished, receipt-owned allocation has never held
                    # a filesystem or been exposed to any application writer.
                    temporary.unlink()
                elif probe.returncode != 0:
                    raise MigrationError("Cannot inspect interrupted allocation")
            if not temporary.exists():
                self.allocate(name, temporary)
                run("cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--uuid", expected_uuid,
                    "--key-file=-", str(temporary), input=recovery)
            if run("cryptsetup", "luksUUID", str(temporary)).decode().strip() != expected_uuid:
                raise MigrationError("Allocation UUID does not match escrow")
            run("cryptsetup", "open", "--test-passphrase", "--key-file=-", str(temporary), input=recovery)
            os.link(temporary, container)
            temporary.unlink()
            run("sync", "-f", str(container.parent))
        if openbao is not None:
            openbao.convert_volume(name, str(container), expected_uuid, record)
        mapping = volume["device"].removeprefix("/dev/mapper/")
        opened = not Path(volume["device"]).exists()
        if not opened:
            # Verifies backing-file identity without requesting a boot credential.
            self.unlock(name)
        else:
            run("cryptsetup", "open", "--type", "luks", "--key-file=-", str(container), mapping, input=recovery)
        complete = False
        try:
            probe = subprocess.run(["blkid", "-p", "-o", "value", "-s", "TYPE", volume["device"]],
                                   capture_output=True, check=False)
            if probe.returncode == 2 and not marker.exists():
                # Only a resumable, escrow-authenticated new volume may gain a filesystem.
                run("mkfs.ext4", "-q", volume["device"])
            elif probe.returncode != 0 or probe.stdout.strip() != b"ext4":
                raise MigrationError("Unexpected or missing filesystem; refusing overwrite")
            run("sync", "-f", str(container))
            atomic_json(marker, identity)
            pending.unlink(missing_ok=True)
            complete = True
        finally:
            if opened and not complete:
                run("cryptsetup", "close", mapping)

    def receipt(self, source, destination, root):
        directory = root / ".luxnix-migrations"
        if directory.exists():
            plain_path(str(directory))
            info = directory.stat()
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise MigrationError("Migration receipt directory must be root-owned mode 0700")
        else:
            directory.mkdir(mode=0o700)
        name = hashlib.sha256(f"{source}\0{destination}".encode()).hexdigest()
        return directory / (name + ".json")

    def identity(self, source, destination):
        uuid = run("findmnt", "-n", "-o", "UUID", "-T", str(destination)).decode().strip()
        if not uuid:
            raise MigrationError("Encrypted destination has no filesystem UUID")
        return {"source": str(source), "destination": str(destination),
                "inode": destination.stat().st_ino,
                "uuid": uuid}

    def pending_copies(self):
        pending = []
        for value, bind in self.config["binds"].items():
            source = plain_path(value)
            root = plain_path(self.config["volumes"][bind["volume"]]["mountPoint"])
            if not os.path.ismount(root):
                raise MigrationError("Encrypted volume is not mounted")
            destination = plain_path(str(root / bind["directory"]))
            self.verifier.encrypted_storage(destination)
            receipt = self.receipt(source, destination, root)
            if receipt.exists():
                plain_path(str(receipt))
                if not destination.is_dir() or json.loads(receipt.read_text()) != self.identity(source, destination):
                    raise MigrationError("Migration receipt does not match its destination")
                continue
            if source.exists() and destination.exists() and os.path.samefile(source, destination):
                atomic_json(receipt, self.identity(source, destination))
                continue
            excludes = [str(Path(path).relative_to(source)) for path in self.config["binds"]
                        if Path(path).is_relative_to(source) and Path(path) != source]
            if source.exists():
                device = source.stat().st_dev
                for directory, children, _ in os.walk(source):
                    children[:] = [name for name in children if
                        str((Path(directory) / name).relative_to(source)) not in excludes]
                    if Path(directory).stat().st_dev != device:
                        raise MigrationError("Unconfigured nested filesystem; declare its bind before migration")
            pending.append((source, destination, receipt, excludes))
        return pending

    def precopy(self):
        for source, destination, _, excludes in self.pending_copies():
            if source.exists():
                staged_copy.precopy(staged_copy.Item(source, destination, tuple(excludes)))

    def prepare(self):
        pending = self.pending_copies()
        if not pending:
            return
        for name in self.config["writers"]:
            if int(run("systemctl", "show", "--value", "-p", "MainPID", name + ".service").strip() or b"0"):
                raise MigrationError("A storage writer is running; migration requires a stopped application")
        try:
            for source, destination, receipt, excludes in pending:
                if not source.exists():
                    if destination.exists():
                        raise MigrationError("Existing encrypted destination differs; refusing overwrite")
                    destination.mkdir(mode=0o700, parents=True)
                    atomic_json(receipt, self.identity(source, destination))
                else:
                    staged_copy.cutover(staged_copy.Item(source, destination, tuple(excludes)), receipt, self.identity)
        except staged_copy.CutoverError as exc:
            raise MigrationError(str(exc)) from None

    def activate_binds(self):
        units = self.config.get("bindUnits", [])
        if units:
            run("systemctl", "start", *units)

    def rollback_copies(self, pending):
        """Return only this attempt's new destinations to private staging."""
        for source, destination, receipt, excludes, existed in reversed(pending):
            if receipt.exists():
                if json.loads(receipt.read_text()) != self.identity(source, destination):
                    raise MigrationError("Cutover rollback receipt changed; refusing to move data")
                receipt.unlink()
            if not existed and destination.exists():
                item = staged_copy.Item(source, destination, tuple(excludes))
                if item.stage.exists():
                    raise MigrationError("Cutover rollback staging path is occupied")
                item.stage.mkdir(mode=0o700)
                atomic_json(item.stage / "plan.json", item.plan)
                destination.rename(item.payload)
                run("sync", "-f", str(item.stage))


MOUNTINFO = Path("/proc/self/mountinfo")
FDINFO = Path("/proc/self/fdinfo")
CONTROL_UNITS = Path("/etc/systemd/system.control")
GENERATED_UNITS = Path("/run/systemd/generator")
OVERRIDE_BACKUPS = Path("/var/lib/luxnix-storage-overrides")


def normalize_mounts(config, *, apply=False):
    """Retire declared native mount overrides without moving data."""
    mounts = {
        v["mountPoint"]: (v["device"], v["fsType"]) for v in config["volumes"].values()
    }
    for target, bind in config["binds"].items():
        volume = config["volumes"][bind["volume"]]
        mounts[target] = (str(Path(volume["mountPoint"]) / bind["directory"]), "none")
    selected = []
    for target, (source, filesystem) in mounts.items():
        unit = (
            run("systemd-escape", "--path", "--suffix=mount", target).decode().strip()
        )
        override, generated = CONTROL_UNITS / unit, GENERATED_UNITS / unit
        if not override.exists() and not override.is_symlink():
            continue
        # Refuse foreign mounts, masks, symlinks and writable or non-root unit files.
        for path in (override, generated):
            info = path.lstat()
            if (
                path.resolve() != path
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != 0
                or info.st_mode & 0o022
            ):
                raise MigrationError("Unsafe mount override or generated replacement")
            definition = configparser.ConfigParser(interpolation=None, strict=False)
            definition.optionxform = str
            text = path.read_text()
            try:
                definition.read_string(text)
            except configparser.Error:
                raise MigrationError(
                    "Cannot parse the declared mount definition"
                ) from None
            # systemd generators repeat dependency directives (including fsck).
            # ConfigParser otherwise keeps only the last value of each key.
            dependencies = {"Requires": [], "After": []}
            section = None
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("["):
                    section = line
                if section == "[Unit]" and "=" in line:
                    key, value = line.split("=", 1)
                    if key in dependencies:
                        if value.endswith("\\"):
                            raise MigrationError(
                                "Review multiline dependency overrides manually"
                            )
                        if not value:
                            dependencies[key].clear()
                        else:
                            dependencies[key].extend(value.split())
            mount = definition["Mount"]
            if (
                mount["What"] != source
                or mount["Where"] != target
                or mount.get("Type", "none") != filesystem
            ):
                raise MigrationError(
                    "Mount override or replacement differs from declared storage"
                )
            if path == generated:
                options = set(mount.get("Options", "").split(","))
                if not set(_required_options(config, target)) <= options:
                    raise MigrationError("Generated mount lacks declared protections")
                if target not in config["binds"]:
                    name = next(
                        name
                        for name, v in config["volumes"].items()
                        if v["mountPoint"] == target
                    )
                    if config["volumes"][name].get("container"):
                        unlock = f"luxnix-storage-unlock-{name}.service"
                        if any(
                            unlock not in dependencies[key]
                            for key in ("Requires", "After")
                        ):
                            raise MigrationError(
                                "Generated mount lacks unlock ordering"
                            )
        fragment = (
            run("systemctl", "show", "--value", "-p", "FragmentPath", unit)
            .decode()
            .strip()
        )
        if fragment != str(override):
            raise MigrationError(
                "A different mount definition is active; inspect before normalization"
            )
        selected.append((override, generated))
    print(
        json.dumps(
            {
                "host": config["machine"],
                "overrides": [str(p) for p, _ in selected],
                "stop_writers": [name + ".service" for name in config["writers"]],
            }
        )
    )
    if not apply or not selected:
        return
    with open("/dev/tty", "w") as output, open("/dev/tty", "r") as reader:
        if not reader.isatty():
            raise MigrationError("A private interactive terminal is required")
        output.write(
            f"Retire only the listed mount overrides? Type {config['machine']}: "
        )
        output.flush()
        if reader.readline().strip() != config["machine"]:
            raise MigrationError("Mount normalization not confirmed")
    for name in config["writers"]:
        state = run(
            "systemctl", "show", "--value", "-p", "ActiveState", name + ".service"
        ).strip()
        if state not in {b"inactive", b"failed"}:
            raise MigrationError(
                "Stop the listed storage writers before normalizing mount overrides"
            )
    root = plain_path(str(OVERRIDE_BACKUPS))
    root.mkdir(mode=0o700, exist_ok=True)
    if root.stat().st_uid != 0 or root.stat().st_mode & 0o077:
        raise MigrationError("Mount override backup directory must be root-only")
    backup = Path(tempfile.mkdtemp(prefix="native-mounts-", dir=root))
    moved = []
    try:
        for override, generated in selected:
            # Copy durably before unlinking; /etc and /var may be different filesystems.
            saved = backup / override.name
            shutil.copy2(override, saved)
            run("sync", "-f", str(saved))
            override.unlink()
            moved.append((override, saved))
        run("sync", "-f", str(CONTROL_UNITS))
        run("systemctl", "daemon-reload")
        for override, generated in selected:
            actual = (
                run("systemctl", "show", "--value", "-p", "FragmentPath", override.name)
                .decode()
                .strip()
            )
            if actual != str(generated):
                raise MigrationError(
                    "Generated mount did not take over; restoring native overrides"
                )
    except BaseException:
        for override, saved in reversed(moved):
            if not override.exists() and not override.is_symlink():
                shutil.copy2(saved, override)
        run("systemctl", "daemon-reload")
        raise
    print(
        f"Mount definitions normalized; original files retained in {backup}. "
        "No data or mounts changed."
    )


def _unescape_mount_field(value):
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def mount_table():
    """Return kernel mount entries by mount ID; path strings alone are ambiguous."""
    entries = {}
    for line in MOUNTINFO.read_text().splitlines():
        left, _, right = line.partition(" - ")
        fields, tail = left.split(), right.split()
        if len(fields) < 6 or len(tail) < 2:
            raise MigrationError("Unreadable kernel mount table")
        entries[int(fields[0])] = {
            "root": _unescape_mount_field(fields[3]),
            "target": _unescape_mount_field(fields[4]),
            "options": fields[5].split(","),
            "source": _unescape_mount_field(tail[1]),
        }
    return entries


def mount_id(path):
    """Kernel mount ID of the directory itself; symlinks are rejected, never followed."""
    fd = os.open(path, os.O_PATH | os.O_NOFOLLOW | os.O_DIRECTORY)
    try:
        for line in (FDINFO / str(fd)).read_text().splitlines():
            if line.startswith("mnt_id:"):
                return int(line.split()[1])
    finally:
        os.close(fd)
    raise MigrationError("Kernel mount identity is unavailable")


def _expected_mount(config, path):
    for volume in config["volumes"].values():
        if volume["mountPoint"] == path:
            return volume["device"], "/"
    bind = config["binds"][path]
    return config["volumes"][bind["volume"]]["device"], "/" + bind["directory"]


def _visible_mount(config, table, path):
    """True only when the path itself is a mount point carrying its configured filesystem."""
    target = Path(path)
    if not target.exists() or target.is_symlink():
        return False
    own = mount_id(target)
    if own == mount_id(target.parent):
        return False
    entry = table.get(own)
    if entry is None or (entry["source"], entry["root"]) != _expected_mount(config, path):
        raise MigrationError(f"{path} carries an unexpected filesystem")
    return True


def _required_options(config, path):
    """Mount protections the Nix module declares for a configured volume or bind."""
    volume = next(
        (v for v in config["volumes"].values() if v["mountPoint"] == path),
        None,
    ) or config["volumes"][config["binds"][path]["volume"]]
    return ["nodev", "nosuid"] + (["noexec"] if volume.get("noexec") else [])


def verify_mounts(config, paths):
    """Fail unless every path is visibly mounted with its configured identity and protections.

    Encrypted ancestry alone is not enough: a different encrypted filesystem,
    or the wrong subdirectory of the right one, must not become a consumer's
    state. Read-only; it never mounts, unmounts or creates anything.
    """
    if not paths:
        raise MigrationError("No storage paths to verify")
    table = mount_table()
    for path in paths:
        if path not in config["binds"] and not any(
            v["mountPoint"] == path for v in config["volumes"].values()
        ):
            raise MigrationError(f"{path} is not a configured operator storage mount")
        if not _visible_mount(config, table, path):
            raise MigrationError(f"{path} is not mounted as configured")
        missing = set(_required_options(config, path)) - set(table[mount_id(Path(path))]["options"])
        if missing:
            raise MigrationError(f"{path} lacks required mount options: {','.join(sorted(missing))}")


def restack_binds(config):
    """Remount nested binds hidden when their parent bind was mounted afterwards.

    A live switch can add a parent bind (for example /etc/secrets) below an
    already mounted child (/etc/secrets/vault). systemd then mounts the parent
    over the child, keeps reporting the child unit active, and the guarded
    consumers fail AssertPathIsMountPoint. Only that state is repaired, only on
    top of a verified encrypted parent, and only while no affected writer runs.
    The hidden stale entry stays attached below the parent until the next boot.
    """
    paths = [v["mountPoint"] for v in config["volumes"].values()] + list(config["binds"])
    table = mount_table()
    for target in sorted(config["binds"], key=lambda p: len(Path(p).parts)):
        ancestors = [p for p in paths if target.startswith(p + "/")]
        if not ancestors:
            continue
        if not any(entry["target"] == target for entry in table.values()):
            continue  # Not mounted at all: its regular mount unit owns that path.
        if _visible_mount(config, table, target):
            continue
        parent = max(ancestors, key=len)
        bind = config["binds"][target]
        volume = config["volumes"][bind["volume"]]
        if not _visible_mount(config, table, parent) or not _visible_mount(config, table, volume["mountPoint"]):
            raise MigrationError(f"{target} is hidden, but its encrypted parent is not mounted as configured")
        for name, guarded in config["guarded"].items():
            if target in guarded and int(
                run("systemctl", "show", "--value", "-p", "MainPID", name + ".service").strip() or b"0"
            ):
                raise MigrationError(f"{name} is running on hidden {target}; stop it before restacking")
        source = plain_path(volume["mountPoint"]) / bind["directory"]
        if source.is_symlink() or not source.is_dir():
            raise MigrationError(f"Bind source for {target} is missing; refusing to create it")
        mountpoint = Path(target)
        if mountpoint.is_symlink() or (mountpoint.exists() and not mountpoint.is_dir()):
            raise MigrationError(f"{target} is not a plain directory")
        if not mountpoint.exists():
            if mountpoint.parent.is_symlink() or mount_id(mountpoint.parent) != mount_id(Path(parent)):
                raise MigrationError(f"{target} would not be created inside {parent}")
            mountpoint.mkdir(mode=0o700)
        options = _required_options(config, target)
        run("mount", "--bind", "-o", ",".join(options), str(source), target)
        table = mount_table()
        if not _visible_mount(config, table, target) or not set(options) <= set(
            table[mount_id(mountpoint)]["options"]
        ):
            raise MigrationError(f"Restacked {target} failed verification")
        print(f"Restacked hidden {target} above {parent}.", file=sys.stderr)



# SHA-256 of the publicly known former fleet admin hash; mirrors modules/nixos/user/admin.
RETIRED_ACCOUNT_HASH_DIGESTS = frozenset({
    "a396e38d2c16276942366260dfc8e88ccef88e5df8915d50e688aca7e1502bba",
})


def private_source(source):
    info = source.stat()
    return stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) in (0o400, 0o600)


def write_account_hash(target, content):
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def prepare_accounts(accounts):
    """Keep each boot copy equal to its source whenever the source is readable.

    The source lives on operator-unlocked storage and is absent before unlock;
    the existing copy then stays authoritative. An existing copy is never
    replaced by an unsafe source or by a retired hash.
    """
    for target, source in accounts.items():
        target, source = plain_path(target), plain_path(source)
        if target.exists():
            if not source.exists():
                continue
            if not private_source(source):
                print(f"WARNING: keeping {target}: its source is not a private root-owned regular file.", file=sys.stderr)
                continue
            content = source.read_bytes()
            if content == target.read_bytes():
                continue
            if hashlib.sha256(content.strip()).hexdigest() in RETIRED_ACCOUNT_HASH_DIGESTS:
                print(f"WARNING: keeping {target}: its source contains a retired shared hash.", file=sys.stderr)
                continue
            write_account_hash(target, content)
            continue
        if not private_source(source):
            raise MigrationError("Boot account hash source must be a private root-owned regular file")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_account_hash(target, source.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument(
        "action", choices=[
            "unlock", "prepare", "precopy", "cutover", "accounts", "provision",
            "restack", "verify", "normalize",
        ]
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("operands", nargs="*")
    args = parser.parse_args()
    if args.apply and args.action != "normalize":
        parser.error("--apply is only supported for normalize")
    if args.action == "verify":
        if not args.operands:
            parser.error("verify requires at least one path")
    elif args.action in {"unlock", "provision"}:
        if len(args.operands) != 1:
            parser.error(f"{args.action} requires exactly one volume")
    elif args.operands:
        parser.error(f"{args.action} takes no operands")
    args.volume = args.operands[0] if args.action in {"unlock", "provision"} else None
    config = json.loads(args.config.read_text())
    spec = importlib.util.spec_from_file_location("storage_verifier", config["verifier"])
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    stopped = []
    rollback = []
    try:
        if os.geteuid() != 0:
            raise MigrationError("Run as root")
        os.umask(0o077)
        if args.action == "verify":
            # Read-only gate: never queue behind an unlock prompt holding the lock.
            verify_mounts(config, args.operands)
            return
        # /run is runtime-only; this lock contains no passphrase or secret data.
        Path("/run/lock").mkdir(mode=0o755, exist_ok=True)
        with open("/run/lock/luxnix-operator-migration", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            migration = Migration(config, verifier)
            if args.action == "unlock":
                migration.unlock(args.volume)
            elif args.action == "provision":
                migration.provision(args.volume, json.loads(sys.stdin.buffer.read(16384)))
            elif args.action == "accounts":
                prepare_accounts(config["accounts"])
            elif args.action == "restack":
                restack_binds(config)
            elif args.action == "normalize":
                normalize_mounts(config, apply=args.apply)
            elif args.action == "precopy":
                migration.precopy()
            elif args.action == "cutover":
                # No bind activation until every final copy and receipt succeeds.
                rollback = [(*item, item[1].exists()) for item in migration.pending_copies()]
                stopped = staged_copy.stop_writers(config["writers"])
                try:
                    migration.prepare()
                except (MigrationError, staged_copy.CutoverError, ValueError, OSError, KeyError):
                    migration.rollback_copies(rollback)
                    raise
            else:
                migration.prepare()
        if args.action == "cutover":
            # Bind units invoke prepare again; release the mutation lock first.
            migration.activate_binds()
            staged_copy.restart_writers(list(dict.fromkeys(stopped + config.get("startupServices", []))))
    except (MigrationError, staged_copy.CutoverError, ValueError, OSError, KeyError) as exc:
        if stopped:
            # Restarts retain the configured encrypted-mount guards. Never clear
            # dependencies or weaken storage checks as part of failure recovery.
            try:
                staged_copy.restart_writers(stopped)
            except staged_copy.CutoverError:
                print("Writer recovery failed; sources retained and storage guards remain enforced.", file=sys.stderr)
        # No subprocess stderr or source contents are emitted.
        print(f"ERROR: encrypted storage preparation: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
