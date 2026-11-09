"""Fresh installation is separate from preservation migration and its journals.

Only an explicit fresh/disposable profile can reach Disko. A started attempt is
never reformatted on retry. Runtime storage checks remain the final authority.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

from lx_administration.secret_storage import encrypted_storage
from lx_administration.storage import boot_migration as migration
from lx_administration.storage.cutover import atomic_json
from lx_administration.utils.file_operations import atomic_create_file


Error = migration.MigrationError


def validate_profile(spec: dict) -> None:
    migration.validate_spec(spec)
    if spec.get("installation") not in {"fresh", "disposable"}:
        raise Error(
            "Select a fresh or disposable profile; use migrate to preserve data"
        )


def validate_config(config: dict) -> None:
    # First supported installer profile: one GPT disk, ESP and one encrypted root.
    # More complex layouts retain their existing administration workflows.
    if len(config["disks"]) != 1 or config["crypttab"].strip():
        raise Error(
            "Fresh installation currently supports one disk and one encrypted root"
        )
    migration.validate_in_place(config)
    if config["secure_boot"] or config["remote_unlock"]["enable"]:
        raise Error(
            "Console unlock only; signed/remote installation needs a separate profile"
        )
    if any(m["fsType"] in {"none", "tmpfs"} for m in config["mounts"].values()):
        raise Error(
            "The fresh profile must use root subvolumes and ESP, without extra mounts"
        )
    if (
        config["secret_contract"]["vault_server"]
        or config["secret_contract"]["openbao"]
    ):
        raise Error("Vault/OpenBao server recovery belongs to a preservation workflow")
    admin = config["admin"]
    if (
        not admin
        or not admin["normal"]
        or not admin["wheel"]
        or not admin["hash_file"]
        or not admin["keys"]
    ):
        raise Error(
            "Prepare a normal administrator with sudo, a password file and SSH keys"
        )


def nix_string(value: str) -> str:
    return json.dumps(value).replace("${", "\\${")


def prepare(profile: Path) -> str:
    spec = yaml.safe_load(profile.read_text())
    validate_profile(spec)
    checkout = Path(spec["checkout"])
    source = migration.source_identity(checkout)
    config = migration.evaluate(checkout, spec["host"])
    validate_config(config)
    if len(spec["disks"]) != 1:
        raise Error("Select exactly one installation disk")
    disk_name = next(iter(config["disks"]))
    config["disks"] = {disk_name: spec["disks"][0]["path"]}
    plan = {"spec": spec, "source": source, "config": config}
    # Nix owns the closure, Disko script and Python runtime in one retained bundle.
    expression = f"""let
      f = builtins.getFlake {nix_string("git+file://" + str(checkout))};
      base = f.nixosConfigurations.{spec["host"]};
      h = base.extendModules {{ modules = [({{ lib, ... }}: {{
        disko.devices.disk.${{{nix_string(disk_name)}}}.device =
          lib.mkForce {nix_string(spec["disks"][0]["path"])};
      }})]; }};
    in import (f.outPath + "/lx_administration/storage/fresh-installer.nix") {{
      pkgs = h.pkgs; source = f.outPath;
      inherit (h.config.system.build) diskoScript;
      disk = builtins.head (builtins.attrValues h.config.disko.devices.disk);
      closure = h.config.system.build.toplevel;
      plan = builtins.fromJSON {nix_string(json.dumps(plan))};
    }}"""
    result = migration.run(
        "nix",
        "build",
        "--impure",
        "--no-update-lock-file",
        "--no-link",
        "--print-out-paths",
        "--expr",
        expression,
        timeout=7200,
    )
    if migration.source_identity(checkout) != source:
        raise Error(
            "Release changed while preparing the installer; discard this result"
        )
    return result


def load_plan(path: Path) -> dict:
    # Bundles are executable releases, not editable operator journals.
    if not str(path).startswith("/nix/store/") or not path.is_file():
        raise Error("Use the immutable plan shipped in the prepared installer bundle")
    plan = json.loads(path.read_text())
    validate_profile(plan["spec"])
    validate_config(plan["config"])
    return plan


def independent(path: Path, disks: set[int]) -> None:
    record = json.loads(
        migration.run(
            "findmnt", "--json", "--target", str(path), "--output", "SOURCE,FSTYPE,UUID"
        )
    )["filesystems"][0]
    if record["fstype"] == "tmpfs":
        raise Error(
            "Keep installer state and credentials on independent persistent media"
        )
    source = record["source"].split("[", 1)[0]
    if (
        not source.startswith("/dev/")
        or migration.device_disks(source) & disks
        or any(
            migration.device_disks(member) & disks
            for member in migration.filesystem_devices(record)
        )
    ):
        raise Error(
            "Installer state or credentials are not on independent physical media"
        )


def credential_files(plan: dict, credentials: Path) -> dict[str, bytes]:
    """Read only explicitly declared inputs; never discover secrets on the old root."""
    migration.private_path(credentials, directory=True)
    encrypted_storage(credentials)
    required = {item["path"] for item in plan["config"]["secret_contract"]["items"]}
    admin = plan["config"]["admin"]
    required.add(admin["hash_file"])
    if admin["source"]:
        required.add(admin["source"])
    values = {}
    for name in sorted(required):
        path = Path(name)
        if not path.is_absolute() or ".." in path.parts or name.startswith("/nix/"):
            raise Error("Invalid credential destination in the evaluated profile")
        source = credentials / name.lstrip("/")
        migration.private_path(source, directory=source.is_dir())
        sources = sorted(source.rglob("*")) if source.is_dir() else [source]
        if not sources:
            raise Error(f"Empty provisioning credential directory: {name}")
        for item in sources:
            migration.private_path(item, directory=item.is_dir())
            if item.is_dir():
                continue
            value = item.read_bytes()
            if not value:
                raise Error(f"Empty provisioning credential: {name}")
            values["/" + str(item.relative_to(credentials))] = value
    account_paths = {
        item["path"]
        for item in plan["config"]["secret_contract"]["items"]
        if item.get("kind") == "account"
    } | {admin["hash_file"]}
    for name in account_paths:
        migration.account_hash(credentials / name.lstrip("/"))
    if admin["source"] and values[admin["source"]] != values[admin["hash_file"]]:
        raise Error("Administrator source and boot hash differ")
    return values


def verify_credential_copies(values: dict[str, bytes]) -> None:
    """A partial provisioning run may keep matching files, never replace them."""
    for name, value in values.items():
        target = Path("/mnt") / name.lstrip("/")
        if target.resolve() != target:
            raise Error("Credential destination contains a symbolic link")
        if target.exists() and migration.target_private(name).read_bytes() != value:
            raise Error(f"Existing credential differs from provisioning media: {name}")


def publish_credentials(values: dict[str, bytes], *, resume: bool = False) -> None:
    if resume:
        # Check every conflict before publishing any missing credential.
        verify_credential_copies(values)
    for name, value in values.items():
        target = Path("/mnt") / name.lstrip("/")
        if target.resolve() != target:
            raise Error("Credential destination contains a symbolic link")
        encrypted_storage(target.parent)
        if resume and target.exists():
            continue
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_create_file(destination=target, content=[value], file_mode=0o600)
        if target.read_bytes() != value:
            raise Error("Provisioned credential verification failed")


def confirm(plan: dict, resume: bool = False) -> None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise Error("Installation requires a private interactive terminal")
    spec = plan["spec"]
    print(f"Install {spec['host']} from revision {plan['source']['revision']}")
    operation = "RESUME" if resume else "ERASE"
    for disk in spec["disks"]:
        print(
            f"{operation} {disk['path']} — serial {disk['serial']} "
            f"— {disk['size_bytes']} bytes"
        )
    if resume:
        print("Continue installation on the verified existing layout; no formatting.")
    else:
        print("All disk contents will be lost. Use migrate to preserve data.")
    print("Keep the disk passphrase off this computer; it is your recovery access.")
    expected = (
        operation
        + " "
        + spec["host"]
        + " "
        + " ".join(d["serial"] for d in spec["disks"])
    )
    if input(f"Type {expected} to authorize this installation: ") != expected:
        raise Error("Installation cancelled before this command changed the target")


def verify_named_devices(plan: dict, disks: set[int]) -> None:
    """Disko's partition labels and mapper names must not select another disk."""
    paths = set(plan["partition_devices"])
    paths.update(m["device"] for m in plan["config"]["mounts"].values())
    for path in paths:
        if path.startswith("/dev/") and os.path.exists(path):
            if not migration.device_disks(path) <= disks:
                raise Error("A partition label or mapper name belongs to another disk")


def preflight(
    plan: dict, state: Path, credentials: Path
) -> tuple[set[int], dict[str, bytes]]:
    disks = migration.probe_disks(plan)
    migration.verify_installer(disks)
    independent(state, disks)
    independent(credentials, disks)
    migration.verify_unmounted_targets(plan)
    verify_named_devices(plan, disks)
    if Path("/mnt").is_symlink() or os.path.ismount("/mnt"):
        raise Error("/mnt must be an unused installer mountpoint")
    return disks, credential_files(plan, credentials)


def recovery_check(
    plan: dict, state: Path, credentials: Path
) -> tuple[dict, set[int], dict[str, bytes]]:
    if (state / "plan.json").exists():
        raise Error("Migration state cannot be reused for fresh installation")
    journal = state / "fresh-install.json"
    migration.private_path(journal)
    record = json.loads(journal.read_text())
    if not isinstance(record, dict) or record.get("plan_id") != migration.digest(plan):
        raise Error(
            "Recovery journal belongs to another prepared installer; "
            "use its original bundle"
        )
    if (
        record.get("status")
        not in {
            "storage-ready",
            "installing",
            "interrupted",
            "installed-awaiting-cold-boot",
        }
        or not isinstance(record.get("mounts"), dict)
        or not record["mounts"]
    ):
        raise Error(
            "No verified storage checkpoint exists; formatting may be incomplete. "
            "Keep this journal and have an administrator inspect the selected disk "
            "from trusted media; --resume never reruns Disko"
        )
    disks = migration.probe_disks(plan)
    migration.verify_installer(disks)
    independent(state, disks)
    independent(credentials, disks)
    verify_named_devices(plan, disks)
    if migration.verify_layout(plan, disks) != record["mounts"]:
        raise Error("Mounted filesystems differ from the recorded storage checkpoint")
    values = credential_files(plan, credentials)
    verify_credential_copies(values)
    return record, disks, values


def install(
    plan: dict, state: Path, credentials: Path, *, apply: bool, resume: bool = False
) -> None:
    if not apply:
        if resume:
            with migration.locked_state(state):
                recovery_check(plan, state, credentials)
            print(
                "Recovery target verified. No changes made; add --apply to resume "
                "installation without formatting."
            )
            return
        disks = migration.probe_disks(plan)
        migration.verify_installer(disks)
        migration.verify_unmounted_targets(plan)
        verify_named_devices(plan, disks)
        print("Target verified. No changes made; add --apply to install.")
        return
    with (
        migration.installer_lock() as lock,
        migration.locked_state(state, create=not resume) as state_lock,
    ):
        lock_fds = tuple(
            dict.fromkeys(fd for fd in (lock, state_lock) if fd is not None)
        )
        if (state / "plan.json").exists():
            raise Error("Migration state cannot be reused for fresh installation")
        journal = state / "fresh-install.json"
        if journal.exists() and not resume:
            raise Error(
                "Attempt already started. Use this bundle with --resume to inspect "
                "recovery; never rerun formatting"
            )
        if resume:
            record, disks, values = recovery_check(plan, state, credentials)
            if record["status"] == "installed-awaiting-cold-boot":
                migration.verify_target(plan, disks)
                if (
                    str(Path("/mnt/nix/var/nix/profiles/system").resolve())
                    != plan["config"]["closure"]
                ):
                    raise Error("Installed system differs from the prepared release")
                print(
                    "Installation already completed; "
                    "cold-boot acceptance is still pending."
                )
                return
        else:
            disks, values = preflight(plan, state, credentials)
        from lx_administration.storage.secret_preflight import verify_admin_password

        verify_admin_password(values[plan["config"]["admin"]["hash_file"]])
        if resume:
            confirm(plan, True)
            if recovery_check(plan, state, credentials) != (record, disks, values):
                raise Error(
                    "Recovery target or credentials changed during confirmation"
                )
        else:
            confirm(plan)
        if not resume and preflight(plan, state, credentials) != (disks, values):
            raise Error("Target or credentials changed during confirmation")
        if not resume:
            record = {"plan_id": migration.digest(plan), "status": "formatting"}
            atomic_json(journal, record)
        # Pass the lock to each mutating child. A crash never authorizes a new erase.
        try:
            if not resume:
                env = {
                    k: v
                    for k, v in os.environ.items()
                    if k not in {"IN_DISKO_TEST", "password", "password_check"}
                }
                subprocess.run(
                    [plan["disko_script"]], check=True, env=env, pass_fds=lock_fds
                )
                identities = migration.verify_layout(plan, disks)
                # Durable identity precedes credentials and system installation.
                record.update(status="storage-ready", mounts=identities)
                atomic_json(journal, record)
            identities = record["mounts"]
            if resume:
                publish_credentials(values, resume=True)
            else:
                publish_credentials(values)
            migration.verify_target(plan, disks)
            record.update(status="installing", mounts=identities)
            atomic_json(journal, record)
            subprocess.run(
                [
                    "nixos-install",
                    "--root",
                    "/mnt",
                    "--system",
                    plan["config"]["closure"],
                    "--no-root-passwd",
                ],
                check=True,
                pass_fds=lock_fds,
            )
            if (
                str(Path("/mnt/nix/var/nix/profiles/system").resolve())
                != plan["config"]["closure"]
            ):
                raise Error("Installed system differs from the prepared release")
            if migration.verify_target(plan, disks) != identities:
                raise Error("Installed storage identity changed")
            record["status"] = "installed-awaiting-cold-boot"
            atomic_json(journal, record)
        except BaseException:
            record["status"] = "interrupted"
            atomic_json(journal, record)
            raise
    print(
        "Encrypted installation verified. Reboot, unlock and log in; "
        "cold-boot acceptance is still pending."
    )


def inspect(host: str, checkout: Path) -> None:
    """Inspect current storage, without creating a migration or install plan."""
    import socket
    from lx_administration.storage import boot

    if socket.gethostname().split(".", 1)[0] != host:
        raise Error("Inspection must run on the named host")
    if not migration.HOST.fullmatch(host):
        raise Error("Invalid host name")
    config = migration.evaluate(checkout, host)
    for path, expected in config["mounts"].items():
        subvolume = next(
            (o for o in expected["options"] if o.startswith("subvol=")), None
        )
        boot.verify_mount(
            path,
            expected["device"],
            expected["fsType"],
            subvolume,
            encrypted=path != "/boot",
        )
    for line in config["crypttab"].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 4:
            raise Error("Unexpected secondary-key contract")
        boot.verify_unlock(
            {"path": fields[2], "device": fields[1], "mapping": fields[0]}
        )
    migration.verify_accounts({"config": config}, Path("/"))
    print("Encrypted storage and administrator hash verified; no changes made.")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(
            "Fresh encrypted installation (default):\n"
            "  devenv shell luxnix --profile /absolute/host.yml\n"
            "Existing encrypted machine: luxnix inspect HOST\n"
            "Preserve existing contents: luxnix migrate\n"
            "No disks changed. Installation requires explicit target approval."
        )
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", metavar="HOST")
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument(
        "--profile",
        type=Path,
        help="Prepare a release bundle from an administrator YAML profile",
    )
    parser.add_argument("--plan", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--resume", action="store_true",
        help="Continue a journaled installation without formatting existing storage",
    )
    args = parser.parse_args(argv)
    try:
        if args.inspect:
            if (
                args.profile
                or args.plan
                or args.apply
                or args.state
                or args.credentials
                or args.resume
            ):
                parser.error("Inspection cannot be combined with installation")
            if os.geteuid() != 0:
                os.execvp(
                    "sudo",
                    [
                        "sudo",
                        sys.executable,
                        "-m",
                        "lx_administration.storage.fresh_install",
                        "--inspect",
                        args.inspect,
                        "--checkout",
                        str(args.checkout),
                    ],
                )
            inspect(args.inspect, args.checkout)
        elif args.profile:
            if args.plan or args.apply or args.state or args.credentials or args.resume:
                parser.error(
                    "--profile prepares a bundle; run that installer separately"
                )
            print(prepare(args.profile) + "/bin/luxnix-install")
        else:
            if not args.plan or not args.state or not args.credentials:
                parser.error(
                    "Prepare with --profile; the bundle needs --state and --credentials"
                )
            install(
                load_plan(args.plan), args.state, args.credentials,
                apply=args.apply, resume=args.resume,
            )
    except (Error, ValueError, OSError, subprocess.SubprocessError) as error:
        print(
            f"STOPPED: {error}. Preserve the journal and provisioning media.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
