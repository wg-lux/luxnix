"""Fleet Secure Boot with a controller-held signing key.

The PKI (PK, KEK, db) exists only age-encrypted in controller custody and, while
a command runs, decrypted in a private tmpfs. The controller signs one host
generation into a staging ESP; the host imports the signed artifacts and its
keyless lanzaboote install registers them. Hosts never hold a private key.

Host-side ``import`` runs from the store with ``python3 -I`` and must not import
other repository modules.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import filecmp
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import ssl
import struct
import time
import uuid
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "conf/secure-boot"
DEFAULT_CUSTODY = Path.home() / ".luxnix-secure-boot/fleet-pki.tar.age"
PROFILE_LINK = re.compile(r"^system-([0-9]+)-link$")
# Content-addressed or generation-addressed files never change once written.
IMMUTABLE = re.compile(
    r"^EFI/(Linux/nixos-generation-[0-9]+(-specialisation-[A-Za-z0-9_.-]+)?-[a-z2-7]+"
    r"|nixos/(kernel|initrd)-[A-Za-z0-9_.+-]+-[a-z2-7]+)\.efi$"
)
BOOTLOADERS = {"EFI/systemd/systemd-bootx64.efi", "EFI/BOOT/BOOTX64.EFI"}
# Kernel and initrd are pinned by hash inside the signed stub, not signed themselves.
SIGNED = re.compile(r"^EFI/(Linux/.*\.efi|systemd/.*\.efi|BOOT/.*\.EFI)$")
PKI_FILES = {
    "GUID",
    *(f"keys/{k}/{k}.{ext}" for k in ("PK", "KEK", "db") for ext in ("key", "pem")),
}
ENROLLMENT_FILES = ("PK.auth", "KEK.auth", "db.auth")
EFIVARS = Path('/sys/firmware/efi/efivars')
X509_GUID = uuid.UUID('a5c059a1-94e4-4aa7-87b5-ab155c2bf072').bytes_le


def enrolled_certificate(database: bytes, certificate: bytes) -> bool:
    """Parse EFI signature lists; a status boolean is not signer identity."""
    offset = 0
    found = False
    while offset < len(database):
        if len(database) - offset < 28:
            raise SecureBootError('Truncated firmware signature database')
        kind = database[offset:offset + 16]
        size, header, entry = struct.unpack_from('<III', database, offset + 16)
        if size < 28 + header or entry < 16 or offset + size > len(database) or (size - 28 - header) % entry:
            raise SecureBootError('Malformed firmware signature database')
        for start in range(offset + 28 + header, offset + size, entry):
            found |= kind == X509_GUID and database[start + 16:start + entry] == certificate
        offset += size
    return found


def firmware_check(certificate: Path, *, enabled_required: bool = True) -> None:
    state = (EFIVARS / 'SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c').read_bytes()
    if len(state) != 5:
        raise SecureBootError('Cannot identify firmware Secure Boot state')
    if state[4] != 1:
        if enabled_required:
            raise SecureBootError('Firmware Secure Boot is disabled; enrollment must finish before changing the boot default')
        return  # Preparation of signed artifacts before explicit firmware enrollment.
    der = ssl.PEM_cert_to_DER_cert(certificate.read_text())
    database = (EFIVARS / 'db-d719b2cb-3d3a-4596-a3bc-dad00e67656f').read_bytes()
    if not enrolled_certificate(database[4:], der):
        raise SecureBootError('The intended signing certificate is not enrolled in firmware db')


class SecureBootError(RuntimeError):
    pass


def run(*args: str | Path, **kwargs) -> str:
    result = subprocess.run(
        [str(a) for a in args], text=True, capture_output=True, check=False, **kwargs
    )
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1:] or ["no error output"]
        raise SecureBootError(f"{Path(str(args[0])).name} failed: {detail[0]}")
    return result.stdout


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SecureBootError(
            f"{name} is required on PATH; run inside the Devenv shell"
        )
    return path


def _require_tty() -> None:
    if not sys.stdin.isatty():
        raise SecureBootError(
            "Secure Boot key operations require an interactive terminal"
        )


@contextmanager
def private_workspace() -> Iterator[Path]:
    """Yield a directory on the caller's private, mode-0700 runtime tmpfs."""
    from lx_administration.secret_storage import encrypted_storage

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    status = runtime.lstat()
    fstype = run("findmnt", "-n", "-o", "FSTYPE", "--target", runtime).strip()
    if (
        runtime.is_symlink()
        or status.st_uid != os.getuid()
        or status.st_mode & 0o777 != 0o700
        or fstype != "tmpfs"
    ):
        raise SecureBootError(
            "Key material requires a private mode-0700 runtime directory on tmpfs"
        )
    encrypted_storage(runtime, allow_runtime=True)
    workspace = Path(tempfile.mkdtemp(prefix="luxnix-secure-boot.", dir=runtime))
    try:
        yield workspace
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _sbctl_config(workspace: Path) -> Path:
    config = workspace / "sbctl.conf"
    config.write_text(f"keydir: {workspace}/pki/keys\nguid: {workspace}/pki/GUID\n")
    return config


def create_keys(custody: Path, public_dir: Path = PUBLIC_DIR) -> None:
    """Create the fleet PKI once; publish db.pem and firmware enrollment files."""
    _require_tty()
    targets = [
        custody,
        public_dir / "db.pem",
        *(public_dir / n for n in ENROLLMENT_FILES),
    ]
    if any(path.exists() for path in targets):
        raise SecureBootError(
            "Fleet Secure Boot keys already exist; never regenerate enrolled keys"
        )
    sbctl, age = _tool("sbctl"), _tool("age")
    with private_workspace() as workspace:
        config = _sbctl_config(workspace)
        run(sbctl, "--quiet", "--config", config, "create-keys")
        exported = workspace / "enroll"
        exported.mkdir()
        # Keep Microsoft certificates so GPU and storage option ROMs still load.
        run(
            sbctl,
            "--quiet",
            "--config",
            config,
            "enroll-keys",
            "--export",
            "auth",
            "--microsoft",
            cwd=exported,
        )
        archive = workspace / "pki.tar"
        with tarfile.open(archive, "w") as tar:
            for name in sorted(PKI_FILES):
                tar.add(workspace / "pki" / name, arcname=name)
        custody.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # age prompts for the custody passphrase on the terminal, twice.
        subprocess.run(
            [age, "--passphrase", "--output", str(custody), str(archive)], check=True
        )
        if (
            decrypt_pki(custody, workspace / "verify")
            != (workspace / "pki/keys/db/db.pem").read_bytes()
        ):
            raise SecureBootError("Custody readback does not match the created keys")
        public_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace / "pki/keys/db/db.pem", public_dir / "db.pem")
        for name in ENROLLMENT_FILES:
            shutil.copyfile(exported / name, public_dir / name)
    print(f"Custody: {custody} (keep an independent encrypted copy).")
    print(f"Commit the public certificate and enrollment files in {public_dir}.")


def decrypt_pki(custody: Path, destination: Path) -> bytes:
    """Decrypt custody into destination (inside a private workspace); return db.pem."""
    age = _tool("age")
    destination.mkdir(mode=0o700)
    archive = destination / "pki.tar"
    subprocess.run(
        [age, "--decrypt", "--output", str(archive), str(custody)], check=True
    )
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        if {m.name for m in members} != PKI_FILES or not all(
            m.isfile() for m in members
        ):
            raise SecureBootError(
                "Custody archive does not contain exactly the fleet PKI"
            )
        tar.extractall(destination / "pki", filter="data")
    archive.unlink()
    return (destination / "pki/keys/db/db.pem").read_bytes()


def stage_artifacts(
    *,
    install_command: str,
    systemd: str,
    toplevel: Path,
    generation: int,
    keys: Path,
    esp: Path,
) -> list[str]:
    """Sign exactly one generation into an empty staging ESP; return its relative files."""
    profiles = esp.parent / "profiles"
    profiles.mkdir()
    (profiles / f"system-{generation}-link").symlink_to(toplevel)
    command = (
        f"{install_command} --public-key={shlex.quote(str(keys / 'db/db.pem'))}"
        f" --private-key={shlex.quote(str(keys / 'db/db.key'))}"
        f" {shlex.quote(str(esp))} {shlex.quote(str(profiles))}/system-*-link"
    )
    environment = {**os.environ, "PATH": f"{systemd}/lib/systemd:{os.environ['PATH']}"}
    run("bash", "-euo", "pipefail", "-c", command, env=environment)
    files = sorted(
        str(p.relative_to(esp))
        for p in esp.rglob("*")
        if p.is_file() and p.parts[len(esp.parts)] == "EFI"
    )
    for name in files:
        if SIGNED.match(name):
            run(_tool("sbverify"), "--cert", keys / "db/db.pem", esp / name)
    return files


def _validated_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = tar.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if (
            not member.isfile()
            or path.is_absolute()
            or ".." in path.parts
            or not (IMMUTABLE.match(member.name) or member.name in BOOTLOADERS)
        ):
            raise SecureBootError(
                f"Unexpected boot artifact in archive: {member.name!r}"
            )
    if not any(m.name.startswith("EFI/Linux/") for m in members):
        raise SecureBootError("Archive contains no signed generation stub")
    return members


def import_artifacts(archive: Path, esp: Path, certificate: Path) -> list[str]:
    """Host side: verify signed artifacts against db.pem, then publish them to the ESP."""
    # Hold one lock across verification/publication; a retry imports identical files.
    descriptor = os.open(esp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _import_artifacts(archive, esp, certificate)
    finally:
        os.close(descriptor)


def _import_artifacts(archive: Path, esp: Path, certificate: Path) -> list[str]:
    sbverify = _tool("sbverify")
    installed = []
    staging = Path(tempfile.mkdtemp(prefix=".luxnix-boot-import.", dir=esp))
    try:
        with tarfile.open(archive) as tar:
            members = _validated_members(tar)
            tar.extractall(staging, members=members, filter="data")
        for member in members:
            if SIGNED.match(member.name):
                run(sbverify, "--cert", certificate, staging / member.name)
        for member in members:
            source, target = staging / member.name, esp / member.name
            if target.exists():
                if filecmp.cmp(source, target, shallow=False):
                    continue
                if member.name not in BOOTLOADERS:
                    raise SecureBootError(
                        f"Refusing to replace differing immutable artifact {member.name}"
                    )
        # Content-addressed payloads first, then stubs, then the two loader copies.
        # Sync each publication so one intact loader remains across an interruption.
        ordered = sorted(members, key=lambda m: (m.name in BOOTLOADERS, m.name.startswith('EFI/Linux/'), m.name))
        for member in ordered:
            source, target = staging / member.name, esp / member.name
            if member.name == 'EFI/BOOT/BOOTX64.EFI' and target.exists():
                # Retain a separately bootable known-good fallback loader until
                # a later explicitly accepted loader refresh; do not replace both.
                run(sbverify, '--cert', certificate, target)
                continue
            if target.exists() and filecmp.cmp(source, target, shallow=False):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            with target.open('rb') as stream:
                os.fsync(stream.fileno())
            os.sync()
            installed.append(member.name)
        os.sync()
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return installed


def _nix(flake: Path, host: str, attribute: str, *, raw: bool = True) -> str:
    target = f"{flake}#nixosConfigurations.{host}.config.{attribute}"
    return run("nix", "eval", "--no-update-lock-file", "--raw" if raw else "--json", target).strip()


def _ssh_target(host: str, inventory: Path) -> list[str]:
    variables = json.loads(
        run(_tool("ansible-inventory"), "-i", inventory, "--host", host)
    )
    address = variables.get("ansible_host", host)
    user = variables.get("ansible_user")
    # Host keys must already be pinned in known_hosts; never trust on first use.
    return ["-o", "StrictHostKeyChecking=yes", f"{user}@{address}" if user else address]


def host_generation(ssh: list[str]) -> tuple[int, str]:
    link = run(
        "ssh", "-o", "BatchMode=yes", *ssh, "readlink", "/nix/var/nix/profiles/system"
    ).strip()
    match = PROFILE_LINK.match(link)
    if not match:
        raise SecureBootError(f"Unexpected system profile link on host: {link!r}")
    target = run(
        "ssh",
        "-o",
        "BatchMode=yes",
        *ssh,
        "readlink",
        "-f",
        f"/nix/var/nix/profiles/{link}",
    ).strip()
    return int(match.group(1)), target


def reviewed_source(flake: Path, inventory: Path) -> str:
    """Require one attributable source for the build, certificate and target."""
    flake = flake.resolve()
    if flake == Path("/tmp") or Path("/tmp") in flake.parents:
        raise SecureBootError("Use a durable reviewed checkout, not /tmp")
    if inventory.resolve() != flake / "ansible/inventory/hosts.ini":
        raise SecureBootError("Use the selected checkout's canonical inventory")
    if run("git", "-C", flake, "status", "--porcelain").strip():
        raise SecureBootError("Review and commit the checkout changes before signing")
    return run("git", "-C", flake, "rev-parse", "HEAD").strip()


def require_generation(ssh: list[str], generation: int, toplevel: str) -> None:
    if host_generation(ssh) != (generation, toplevel):
        raise SecureBootError("The selected host generation changed; stop and review it again")


def finish_generation(ssh: list[str], generation: int, toplevel: str, action: str,
                      receipt: str | None = None) -> None:
    """Finish only the reviewed generation; never reboot or select another profile."""
    if action not in {"boot", "switch"}:
        raise SecureBootError("Choose boot (next start) or switch (activate now)")
    require_generation(ssh, generation, toplevel)
    subprocess.run(['ssh', '-t', *ssh, 'sudo', f'{toplevel}/sw/bin/luxnix-boot-artifacts', 'verify-firmware'], check=True)
    command = [f'{toplevel}/sw/bin/luxnix-safe-activate', 'start', '--system', toplevel, '--action', action]
    if receipt:
        command += ['--receipt', receipt]
    identifier = subprocess.run(['ssh', '-t', *ssh, shlex.join(['sudo', '--', *command])], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
    if not re.fullmatch('[a-f0-9]{24}', identifier):
        raise SecureBootError('Could not identify detached activation; inspect its host-side recovery journal')
    # Every status probe starts a new authenticated connection; never acknowledge
    # success through the activation session or a cached ControlMaster transport.
    for _ in range(390):
        try:
            state = json.loads(run('ssh', '-o', 'BatchMode=yes', '-o', 'ControlMaster=no',
                                  '-o', 'ControlPath=none', '-o', 'ConnectTimeout=5', *ssh,
                                  f'{toplevel}/sw/bin/luxnix-safe-activate', 'status', '--id', identifier))
            if state['status'] == 'accepted':
                break
            if state['status'] == 'awaiting-ack':
                subprocess.run(['ssh', '-t', '-o', 'ControlMaster=no', '-o', 'ControlPath=none', *ssh,
                    'sudo', f'{toplevel}/sw/bin/luxnix-safe-activate', 'ack', '--id', identifier], check=True)
                break
        except (SecureBootError, json.JSONDecodeError, KeyError):
            state = {}
        if state.get('status') in {'rolled-back', 'recovering'}:
            raise SecureBootError('Activation did not retain access; the compatible previous generation is being restored')
        time.sleep(5)
    else:
        raise SecureBootError('No fresh authenticated completion; host watchdog will restore the approved compatible generation')
    require_generation(ssh, generation, toplevel)
    if action == "switch":
        current = run("ssh", "-o", "BatchMode=yes", *ssh,
                      "readlink", "-f", "/run/current-system").strip()
        if current != toplevel:
            raise SecureBootError("Activation did not select the reviewed system; retain recovery access")


def sign_host(host: str, flake: Path, custody: Path, inventory: Path,
              finish: str | None = None, receipt: str | None = None) -> None:
    """Sign the host's current profile generation if it is the reviewed configuration."""
    _require_tty()
    flake = flake.resolve()
    if not re.fullmatch(r"[a-z][a-z0-9-]*", host):
        raise SecureBootError("Select one inventory host by name")
    revision = reviewed_source(flake, inventory)
    if _nix(flake, host, "system.boot.secureBoot", raw=False) != "true":
        raise SecureBootError(f"{host} does not enable system.boot.secureBoot")
    certificate = (flake / "conf/secure-boot/db.pem").read_bytes()
    # Building locally means the signed content never comes from the host.
    toplevel = run(
        "nix",
        "build",
        "--no-update-lock-file",
        "--no-link",
        "--print-out-paths",
        f"{flake}#nixosConfigurations.{host}.config.system.build.toplevel",
    ).strip()
    run(
        "nix",
        "build",
        "--no-update-lock-file",
        "--no-link",
        f"{flake}#nixosConfigurations.{host}.config.boot.loader.external.installHook",
    )
    install_command = _nix(flake, host, "boot.lanzaboote.installCommand")
    systemd = _nix(flake, host, "systemd.package.outPath")
    run("bash", flake / "scripts/check-connectivity.sh", host, cwd=flake)
    ssh = _ssh_target(host, inventory)
    if run("ssh", "-o", "BatchMode=yes", *ssh, "hostname").strip() != host:
        raise SecureBootError("The responding host does not match your selected host")
    generation, profile_target = host_generation(ssh)
    if profile_target != toplevel:
        raise SecureBootError(
            f"{host} system profile {profile_target} is not the reviewed build {toplevel}; "
            "run the rebuild first and sign only the reviewed revision"
        )
    confirmation = f"sign {host} generation {generation}" + (f" and {finish}" if finish else "")
    print(f"Host: {host}; revision: {revision}; generation: {generation}; system: {toplevel}")
    print("This installs signed boot files. " + (
        "It also activates services now." if finish == "switch" else
        "It also sets up the next boot; it does not reboot." if finish == "boot" else
        "It does not activate services or reboot."))
    if input(f"Type '{confirmation}' to continue: ").strip() != confirmation:
        raise SecureBootError("Cancelled; no boot files were delivered")
    with private_workspace() as workspace:
        if decrypt_pki(custody, workspace / "custody") != certificate:
            raise SecureBootError(
                "Custody db.pem does not match conf/secure-boot/db.pem"
            )
        esp = workspace / "stage/esp"
        esp.mkdir(parents=True)
        files = stage_artifacts(
            install_command=install_command,
            systemd=systemd,
            toplevel=Path(toplevel),
            generation=generation,
            keys=workspace / "custody/pki/keys",
            esp=esp,
        )
        shutil.rmtree(workspace / "custody")
        archive = workspace / "artifacts.tar"
        with tarfile.open(archive, "w") as tar:
            for name in files:
                tar.add(esp / name, arcname=name)
        if reviewed_source(flake, inventory) != revision:
            raise SecureBootError("The reviewed source changed during signing")
        require_generation(ssh, generation, toplevel)
        remote = run("ssh", "-o", "BatchMode=yes", *ssh, "mktemp", "-d").strip()
        try:
            run(
                "scp",
                "-o",
                "BatchMode=yes",
                *ssh[:-1],
                archive,
                f"{ssh[-1]}:{remote}/artifacts.tar",
            )
            subprocess.run(
                [
                    "ssh",
                    "-t",
                    *ssh,
                    "sudo",
                    f"{toplevel}/sw/bin/luxnix-boot-artifacts",
                    "import",
                    f"{remote}/artifacts.tar",
                ],
                check=True,
            )
        finally:
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", *ssh, "rm", "-rf", "--", remote],
                check=False,
            )
    if finish:
        finish_generation(ssh, generation, toplevel, finish, receipt)
        print(f"Verified {finish} for {host}, generation {generation}. No reboot was requested.")
        return
    print(f"Signed generation {generation} of {host}. On the host run:")
    print(
        "  sudo /nix/var/nix/profiles/system/bin/switch-to-configuration boot   # or switch"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "create-keys", help="create the fleet PKI once on the controller"
    )
    create.add_argument("--custody", type=Path, default=DEFAULT_CUSTODY)
    sign = commands.add_parser(
        "sign", help="sign one host's current reviewed generation"
    )
    sign.add_argument("host")
    sign.add_argument("--flake", type=Path, default=ROOT)
    sign.add_argument("--custody", type=Path, default=DEFAULT_CUSTODY)
    sign.add_argument("--finish", choices=("boot", "switch"),
                      help="after verified import, explicitly stage boot or activate services; never reboot")
    sign.add_argument('--rollback-receipt', help='root-private target path to exact-closure compatibility assessment when footprints differ')
    sign.add_argument(
        "--inventory", type=Path, default=ROOT / "ansible/inventory/hosts.ini"
    )
    host_import = commands.add_parser(
        "import", help="host side: verify and publish signed artifacts"
    )
    host_import.add_argument("--esp", type=Path, required=True)
    host_import.add_argument("--cert", type=Path, required=True)
    host_import.add_argument("archive", type=Path)
    firmware = commands.add_parser('verify-firmware', help='verify live firmware trusts the intended signer')
    firmware.add_argument('--cert', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create-keys":
            create_keys(args.custody)
        elif args.command == "sign":
            sign_host(args.host, args.flake, args.custody, args.inventory, args.finish, args.rollback_receipt)
        elif args.command == 'verify-firmware':
            firmware_check(args.cert)
        else:
            firmware_check(args.cert, enabled_required=False)
            for name in import_artifacts(args.archive, args.esp, args.cert):
                print(f"Installed {name}")
    except (
        SecureBootError,
        ValueError,
        subprocess.CalledProcessError,
        OSError,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
