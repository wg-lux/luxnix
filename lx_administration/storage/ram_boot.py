"""Prepare and start host-bound RAM images without operator-entered store paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import socket
import stat
import subprocess

from lx_administration import secure_boot as sb
from lx_administration.utils.file_operations import atomic_write_file
from lx_administration.yaml import load_unique_yaml_file


def state_dir(host: str) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", host):
        raise ValueError("Select one inventory host")
    return Path.home() / ".local/state/luxnix/ram" / host


def save(path: Path, value: dict) -> None:
    import yaml

    if path.resolve() != path:
        raise ValueError("RAM metadata must not use symbolic links")
    atomic_write_file(
        destination=path,
        content=[yaml.safe_dump(value).encode()],
        file_mode=0o600,
        dir_mode=0o700,
    )


def load(path: Path) -> dict:
    info = path.lstat()
    if (
        path.resolve() != path
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("RAM metadata must be private and owned by this operator")
    value = load_unique_yaml_file(path)
    if not isinstance(value, dict):
        raise ValueError("Invalid RAM metadata; run luxnix ram push again")
    return value


def hashes(bundle: Path) -> dict:
    from lx_administration.storage.migration_boot import digest

    if (
        bundle.parent != Path("/nix/store")
        or bundle.resolve() != bundle
        or not re.fullmatch(r"[a-z0-9]{32}-.+", bundle.name)
    ):
        raise ValueError("RAM bundles must be immutable Nix store outputs")
    return {
        name: digest(bundle / name)
        for name in ("kernel", "initrd", "cmdline", "manifest.json")
    }


def prepare_local(data: dict, source: str) -> dict:
    """Runs on the selected host; no sudo, kernel loading or boot activation."""
    from lx_administration.storage import migration_boot as boot

    host, root = data["host"], Path(data["checkout"])
    if socket.gethostname().split(".")[0] != host:
        raise ValueError("RAM preparation reached another host")
    if (
        sb.reviewed_source(root, root / "ansible/inventory/hosts.ini")
        != data["revision"]
    ):
        raise ValueError("Target checkout differs from the selected revision")
    directory = state_dir(host)
    settings = data["settings"]
    settings_id = hashlib.sha256(
        json.dumps(settings, sort_keys=True).encode()
    ).hexdigest()
    settings_file = directory / f"settings-{settings_id}.yml"
    save(settings_file, settings)
    args = argparse.Namespace(
        host=host,
        settings=settings_file,
        **{name: None for name in boot.BUILD_SETTINGS},
    )
    spec = boot.reviewed_spec(args, root, "host-kexec", "tty1")
    bundle = boot.build_attribute(root, spec, "kexecBundle")
    if json.loads((bundle / "manifest.json").read_text()) != spec:
        raise ValueError("Built RAM manifest differs from the reviewed settings")
    if (
        sb.reviewed_source(root, root / "ansible/inventory/hosts.ini")
        != data["revision"]
    ):
        raise ValueError("Target source changed during preparation")
    receiver = directory / "receiver.py"
    receiver_hash = hashlib.sha256(source.encode()).hexdigest()
    atomic_write_file(destination=receiver, content=[source.encode()], file_mode=0o600)
    receipt = {
        "host": host,
        "checkout": str(root),
        "revision": spec["revision"],
        "bundle": str(bundle),
        "hashes": hashes(bundle),
        "receiver": str(receiver),
        "receiver_sha256": receiver_hash,
    }
    save(directory / "prepared.yml", receipt)
    return receipt


def start_local(host: str, root: str, apply: bool) -> int:
    """Verify the saved preparation before entering the existing kexec command."""
    from lx_administration.storage.migration_boot import validate_spec

    if socket.gethostname().split(".")[0] != host:
        raise ValueError("Run this RAM image on its selected host")
    receipt = load(state_dir(host) / "prepared.yml")
    if (
        receipt["host"] != host
        or receipt["checkout"] != root
        or sb.reviewed_source(Path(root), Path(root) / "ansible/inventory/hosts.ini")
        != receipt["revision"]
    ):
        raise ValueError("Prepared RAM source changed; run luxnix ram push again")
    bundle = Path(receipt["bundle"])
    if hashes(bundle) != receipt["hashes"]:
        raise ValueError("Prepared RAM artifacts changed; nothing was loaded")
    spec = json.loads((bundle / "manifest.json").read_text())
    validate_spec(spec)
    if (
        spec["host"] != host
        or spec["revision"] != receipt["revision"]
        or spec["boot_trust"] != "host-kexec"
    ):
        raise ValueError("Prepared RAM identity differs; nothing was loaded")
    wrapper = (
        "let p=f.inputs.nixpkgs.legacyPackages.x86_64-linux; "
        's=(import (f.outPath + "/devenv/scripts.nix") {pkgs=p;}).migration-boot.exec; '
        'in p.writeShellScriptBin "migration-boot" '
        '("export PYTHONPATH=${f.outPath}\n" + s)'
    )
    command = [
        "nix",
        "shell",
        "--impure",
        "--expr",
        flake_expression(root, receipt["revision"], wrapper),
        "--command",
        "migration-boot",
        "kexec",
        host,
        "--bundle",
        str(bundle),
    ]
    if apply:
        command.append("--apply")
    print(f"RAM image for {host}, revision {receipt['revision'][:12]}", flush=True)
    return subprocess.call(
        command,
        cwd=root,
        env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
        | {"UV_PROJECT_ENVIRONMENT": f"{root}/.devenv/state/venv"},
    )


def target(host: str, root: Path) -> tuple[list[str], str]:
    state_dir(host)  # Validate before resolving inventory or opening SSH.
    inventory = root / "ansible/inventory/hosts.ini"
    values = json.loads(sb.run("ansible-inventory", "-i", inventory, "--host", host))
    checkout = values.get("luxnix_dev_repo")
    if (
        not values.get("ansible_host")
        or not isinstance(checkout, str)
        or not checkout.startswith("/")
    ):
        raise ValueError("Inventory must declare the host address and durable checkout")
    return sb._ssh_target(host, inventory), checkout


def flake_expression(root: str, revision: str, result: str) -> str:
    uri = "git+file://" + root + "?rev=" + revision
    return f"let f=builtins.getFlake {json.dumps(uri)}; in {result}"


def remote_command(root: str, code: str, data: dict) -> str:
    # Bare SSH sessions need not have uv/devenv on PATH. Obtain the same pinned
    # uv package used by the contributor shell, under normal target Nix trust.
    expression = flake_expression(
        root, data["revision"], "f.inputs.nixpkgs.legacyPackages.x86_64-linux.uv"
    )
    command = [
        "nix",
        "shell",
        "--impure",
        "--expr",
        expression,
        "--command",
        "env",
        f"UV_PROJECT_ENVIRONMENT={root}/.devenv/state/venv",
        f"PYTHONPATH={root}",
        "uv",
        "run",
        "--locked",
        "python",
        "-c",
        code,
        json.dumps(data),
    ]
    return f"cd {shlex.quote(root)} && exec {shlex.join(command)}"


def push(args) -> None:
    host = args.host
    ssh, checkout = target(host, args.flake)
    settings_file = args.settings or state_dir(host) / "settings.yml"
    settings = load_unique_yaml_file(settings_file)
    if not isinstance(settings, dict) or settings.get("host") != host:
        raise ValueError("Supply settings for this host with --settings <settings.yml>")
    revision = sb.run("git", "-C", args.flake, "rev-parse", "HEAD").strip()
    source = Path(__file__).read_text()
    data = {
        "host": host,
        "checkout": checkout,
        "revision": revision,
        "settings": settings,
    }
    bootstrap = (
        "import json,sys; x=json.load(sys.stdin); n={'__name__':'ram_receiver'}; "
        "exec(x['source'],n); "
        "print(json.dumps(n['prepare_local'](x['data'],x['source'])))"
    )
    print(
        f"Preparing {host} from its clean checkout at {revision[:12]}; no RAM start.",
        flush=True,
    )
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            *ssh,
            remote_command(checkout, bootstrap, {"revision": revision}),
        ],
        input=json.dumps({"source": source, "data": data}),
        text=True,
        stdout=subprocess.PIPE,
        check=True,
        timeout=3600,
    )
    receipt = json.loads(result.stdout)
    if receipt.get("host") != host or receipt.get("revision") != revision:
        raise ValueError("Remote preparation returned another host or revision")
    save(state_dir(host) / "prepared.yml", receipt)
    save(state_dir(host) / "settings.yml", settings)
    print(f"Prepared. Start with: luxnix ram {host} --apply")
    print("This still requires private sudo prompts and START RAM confirmation.")


def start(args) -> int:
    host = args.host or socket.gethostname().split(".")[0]
    receipt = load(state_dir(host) / "prepared.yml")
    if host == socket.gethostname().split(".")[0]:
        return start_local(host, receipt["checkout"], args.apply)
    ssh, checkout = target(host, args.flake)
    if receipt["host"] != host or receipt["checkout"] != checkout:
        raise ValueError("Inventory changed; run luxnix ram push again")
    bootstrap = """import json,sys,hashlib
from pathlib import Path
x=json.loads(sys.argv[1])
s=Path(x['receiver']).read_bytes()
if hashlib.sha256(s).hexdigest()!=x['receiver_sha256']:
    raise ValueError('RAM helper changed; run luxnix ram push again')
n={'__name__':'ram_receiver'}
exec(compile(s,x['receiver'],'exec'),n)
sys.exit(n['start_local'](x['host'],x['checkout'],x['apply']))
"""
    data = receipt | {"apply": args.apply}
    print(
        "Use this terminal for sudo. Before START RAM, copy the printed known_hosts "
        "file to the controller; do not rerun the command while waiting.",
        flush=True,
    )
    return subprocess.call(
        ["ssh", "-tt", *ssh, remote_command(checkout, bootstrap, data)]
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action_or_host", nargs="?")
    parser.add_argument("host", nargs="?")
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--flake", type=Path, default=sb.ROOT)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action_or_host == "push":
            if not args.host or args.apply:
                parser.error(
                    "push prepares one HOST only; "
                    "start separately with ram HOST --apply"
                )
            push(args)
        else:
            if args.host or args.settings:
                parser.error(
                    "use ram [HOST] [--apply], or ram push HOST --settings FILE"
                )
            args.host = args.action_or_host
            raise SystemExit(start(args))
    except (
        ValueError,
        KeyError,
        OSError,
        sb.SecureBootError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(
            1, f"RAM preparation/start stopped: {error}. No formatting is authorized.\n"
        )
