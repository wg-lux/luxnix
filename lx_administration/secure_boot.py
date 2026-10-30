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
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            installed.append(member.name)
        os.sync()
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return installed


def _nix(flake: Path, host: str, attribute: str, *, raw: bool = True) -> str:
    target = f"{flake}#nixosConfigurations.{host}.config.{attribute}"
    return run("nix", "eval", "--raw" if raw else "--json", target).strip()


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


def sign_host(host: str, flake: Path, custody: Path, inventory: Path) -> None:
    """Sign the host's current profile generation if it is the reviewed configuration."""
    _require_tty()
    if _nix(flake, host, "system.boot.secureBoot", raw=False) != "true":
        raise SecureBootError(f"{host} does not enable system.boot.secureBoot")
    certificate = (PUBLIC_DIR / "db.pem").read_bytes()
    # Building locally means the signed content never comes from the host.
    toplevel = run(
        "nix",
        "build",
        "--no-link",
        "--print-out-paths",
        f"{flake}#nixosConfigurations.{host}.config.system.build.toplevel",
    ).strip()
    run(
        "nix",
        "build",
        "--no-link",
        f"{flake}#nixosConfigurations.{host}.config.boot.loader.external.installHook",
    )
    install_command = _nix(flake, host, "boot.lanzaboote.installCommand")
    systemd = _nix(flake, host, "systemd.package.outPath")
    ssh = _ssh_target(host, inventory)
    generation, profile_target = host_generation(ssh)
    if profile_target != toplevel:
        raise SecureBootError(
            f"{host} system profile {profile_target} is not the reviewed build {toplevel}; "
            "run the rebuild first and sign only the reviewed revision"
        )
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
    sign.add_argument(
        "--inventory", type=Path, default=ROOT / "ansible/inventory/hosts.ini"
    )
    host_import = commands.add_parser(
        "import", help="host side: verify and publish signed artifacts"
    )
    host_import.add_argument("--esp", type=Path, required=True)
    host_import.add_argument("--cert", type=Path, required=True)
    host_import.add_argument("archive", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "create-keys":
            create_keys(args.custody)
        elif args.command == "sign":
            sign_host(args.host, args.flake, args.custody, args.inventory)
        else:
            for name in import_artifacts(args.archive, args.esp, args.cert):
                print(f"Installed {name}")
    except (
        SecureBootError,
        subprocess.CalledProcessError,
        OSError,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
