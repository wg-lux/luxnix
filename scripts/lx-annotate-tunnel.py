#!/usr/bin/env python3
"""Open one host's lx-annotate browser UI through a scoped SSH tunnel."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lx_administration.yaml import load_unique_yaml_file

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_ROOT = REPO_ROOT / "ansible/inventory"
DEFAULT_VHOST = "lx-annotate.local"
VHOST_KEY = "luxnix.lxAnnotateLocal.django.hostname"
KEYCLOAK_KEY = "generic_settings.network.keycloak.domain"
PUBLIC_CERTIFICATE = "/run/lx-annotate-ssl/lx-annotate-selfsigned.crt"
HUB_EXPORT_PAGE = "/hub-export"
REQUIRED_UNITS = ("lx-annotate.service", "nginx.service")
HUB_UNITS = (
    "lx-annotate-celery-hub-transfer-worker.service",
    "lx-annotate-hub-node-provisioning.service",
)
CERTIFICATE_MARKER = "---lx-annotate-tunnel-certificate---"
HOSTNAME_PATTERN = re.compile(r"[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?")
PAGE_PATTERN = re.compile(r"/[A-Za-z0-9/_.~-]*")
SOCKS_FAILURES = {
    1: "general failure",
    2: "destination not permitted by the SSH server",
    3: "network unreachable",
    4: "host unreachable",
    5: "connection refused",
}


class TunnelError(RuntimeError):
    """Operator-facing failure; the message names the next step."""


@dataclass(frozen=True)
class Target:
    host: str
    vhost: str
    keycloak: str

    def url(self, page: str) -> str:
        return f"https://{self.vhost}{page}"


def inventory_hosts(inventory_path: Path) -> set[str]:
    """Return every host declared with an address in the inventory."""
    hosts: set[str] = set()
    for raw_line in inventory_path.read_text(encoding="utf-8").splitlines():
        fields = shlex.split(raw_line, comments=True)
        if fields and any(field.startswith("ansible_host=") for field in fields[1:]):
            hosts.add(fields[0])
    return hosts


def _unquote(value: object, label: str) -> str:
    text = str(value).strip().strip('"')
    if not HOSTNAME_PATTERN.fullmatch(text):
        raise TunnelError(f"{label} is not a plain host name: {value!r}")
    return text


def _find_key(node: Any, key: str) -> object | None:
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for child in node.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def resolve_target(host: str, inventory_root: Path = INVENTORY_ROOT) -> Target:
    if host not in inventory_hosts(inventory_root / "hosts.ini"):
        raise TunnelError(f"{host!r} is not a host in ansible/inventory/hosts.ini")

    vhost = DEFAULT_VHOST
    host_vars = inventory_root / "host_vars" / f"{host}.yml"
    if host_vars.is_file():
        configured = _find_key(load_unique_yaml_file(host_vars), VHOST_KEY)
        if configured is not None:
            vhost = _unquote(configured, f"{host_vars.name}: {VHOST_KEY}")

    shared = inventory_root / "group_vars/all/30-nix.yml"
    keycloak = _find_key(load_unique_yaml_file(shared), KEYCLOAK_KEY)
    if keycloak is None:
        raise TunnelError(f"{KEYCLOAK_KEY} is missing from {shared}")
    return Target(host, vhost, _unquote(keycloak, KEYCLOAK_KEY))


def certificate_fingerprint(pem: str) -> str | None:
    """SHA-256 fingerprint of the first PEM certificate, as browsers show it."""
    if "BEGIN CERTIFICATE" not in pem:
        return None
    digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.strip())).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def remote_preflight(target: Target) -> tuple[dict[str, str], str | None]:
    """Read service states and the public certificate; changes nothing."""
    units = REQUIRED_UNITS + HUB_UNITS
    remote = (
        f"systemctl is-active {' '.join(units)}; "
        f"echo {CERTIFICATE_MARKER}; cat {PUBLIC_CERTIFICATE} 2>/dev/null"
    )
    result = subprocess.run(
        ["ssh", "-T", "-o", "ConnectTimeout=10", target.host, remote],
        check=False,
        capture_output=True,
        text=True,
    )
    states_text, marker, certificate = result.stdout.partition(CERTIFICATE_MARKER)
    states = states_text.split()
    if not marker or len(states) != len(units):
        detail = result.stderr.strip().splitlines()[-1:] or ["no output"]
        raise TunnelError(
            f"SSH to {target.host} failed ({detail[0]}). "
            f"Run: devenv shell check-connectivity {target.host}"
        )
    return dict(zip(units, states, strict=True)), certificate_fingerprint(certificate)


def free_local_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def ssh_tunnel_command(host: str, port: int) -> list[str]:
    return [
        "ssh",
        "-N",
        "-T",
        "-D",
        f"127.0.0.1:{port}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        host,
    ]


def _receive(connection: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


def socks_connect_check(port: int, vhost: str, timeout: float = 15.0) -> None:
    """Ask the tunnel to open vhost:443 by name; raise when the server refuses."""
    name = vhost.encode("ascii")
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
        connection.sendall(b"\x05\x01\x00")
        if _receive(connection, 2) != b"\x05\x00":
            raise TunnelError("the local tunnel endpoint did not answer as SOCKS5")
        connection.sendall(
            b"\x05\x01\x00\x03" + bytes([len(name)]) + name + (443).to_bytes(2, "big")
        )
        reply = _receive(connection, 2)
    if len(reply) < 2 or reply[1] != 0:
        reason = (
            SOCKS_FAILURES.get(reply[1], "refused")
            if len(reply) == 2
            else ("forwarding rejected by the SSH server")
        )
        raise TunnelError(
            f"the tunnel cannot reach {vhost}:443 ({reason}). The host must run a "
            "configuration with services.luxnix.lxAnnotateLocal.remoteAccess."
            "sshTunnel.enable = true; see docs/lx-annotate-remote-tunnel.md."
        )


def wait_for_tunnel(
    process: subprocess.Popen[bytes], port: int, timeout: float = 30.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise TunnelError(
                f"ssh exited with status {process.returncode} before the tunnel opened"
            )
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
            return
        except OSError:
            time.sleep(0.2)
    raise TunnelError("the SSH tunnel did not open within 30 seconds")


def firefox_preferences(port: int, keycloak: str) -> str:
    """Send everything except the Keycloak login through the tunnel.

    The profile has no direct route to the lx-annotate name, so a closed
    tunnel fails instead of reaching the controller's own instance.
    """
    preferences: dict[str, object] = {
        "network.proxy.type": 1,
        "network.proxy.socks": "127.0.0.1",
        "network.proxy.socks_port": port,
        "network.proxy.socks_version": 5,
        "network.proxy.socks_remote_dns": True,
        "network.proxy.socks5_remote_dns": True,
        "network.proxy.no_proxies_on": keycloak,
        "network.proxy.failover_direct": False,
        "network.proxy.allow_bypass": False,
        "network.trr.mode": 5,
        "network.dns.disablePrefetch": True,
        "network.prefetch-next": False,
        "browser.shell.checkDefaultBrowser": False,
        "browser.aboutwelcome.enabled": False,
        "browser.startup.homepage_override.mstone": "ignore",
        "datareporting.policy.dataSubmissionEnabled": False,
    }

    def render(value: object) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    return "".join(
        f'user_pref("{name}", {render(value)});\n'
        for name, value in preferences.items()
    )


def profile_directory(host: str) -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return state_home / "luxnix/lx-annotate-tunnel" / host


def prepare_profile(directory: Path, port: int, keycloak: str) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    (directory / "user.js").write_text(
        firefox_preferences(port, keycloak), encoding="utf-8"
    )


def report_preflight(
    target: Target, states: dict[str, str], fingerprint: str | None
) -> None:
    for unit, state in states.items():
        print(f"  {unit}: {state}")
    stopped = [unit for unit in REQUIRED_UNITS if states[unit] != "active"]
    if stopped:
        raise TunnelError(
            f"{', '.join(stopped)} not active on {target.host}; nothing to open. "
            "If its data volume is locked, run 'sudo luxnix-operator-storage start' "
            "there."
        )
    if any(states[unit] != "active" for unit in HUB_UNITS):
        print(
            "WARNING: hub transfer services are not active; marked resources will not "
            "be sent until an administrator restores them.",
            file=sys.stderr,
        )
    if fingerprint:
        print(
            "Self-signed TLS certificate SHA-256, read over SSH. Accept the browser "
            f"warning only if it shows this fingerprint:\n  {fingerprint}"
        )


def run_session(target: Target, page: str, port: int, browser: bool) -> int:
    tunnel = subprocess.Popen(
        ssh_tunnel_command(target.host, port), stdin=subprocess.DEVNULL
    )
    try:
        wait_for_tunnel(tunnel, port)
        socks_connect_check(port, target.vhost)
        url = target.url(page)
        if browser:
            profile = profile_directory(target.host)
            prepare_profile(profile, port, target.keycloak)
            print(
                f"Opening {url} on {target.host}; close the browser to end the tunnel."
            )
            session = subprocess.Popen(
                [
                    "firefox",
                    "--no-remote",
                    "--new-instance",
                    "--profile",
                    str(profile),
                    url,
                ]
            )
        else:
            print(
                f"SOCKS5 tunnel to {target.host} on 127.0.0.1:{port} (remote DNS).\n"
                f"Open {url} with a browser profile that proxies everything except "
                f"{target.keycloak}. Press Ctrl-C to close."
            )
            session = None
        while tunnel.poll() is None and (session is None or session.poll() is None):
            time.sleep(0.5)
        if tunnel.poll() is not None:
            raise TunnelError(
                f"the SSH tunnel to {target.host} closed (status {tunnel.returncode}); "
                "the browser window can no longer reach the host."
            )
        return 0
    except KeyboardInterrupt:
        return 130
    finally:
        if tunnel.poll() is None:
            tunnel.terminate()
            tunnel.wait(timeout=10)


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lx-annotate-tunnel",
        description=(
            "Open lx-annotate on one inventory host through an SSH tunnel to annotate "
            "videos or mark resources for hub export. Sign in with your own account."
        ),
    )
    parser.add_argument("host", help="inventory host, for example gc-05")
    pages = parser.add_mutually_exclusive_group()
    pages.add_argument("--page", default="/", help="start path (default: /)")
    pages.add_argument(
        "--hub-export",
        dest="page",
        action="store_const",
        const=HUB_EXPORT_PAGE,
        help=f"start on the Hub Export page ({HUB_EXPORT_PAGE})",
    )
    parser.add_argument(
        "--port", type=int, help="local tunnel port (default: a free port)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="only hold the tunnel open and print its endpoint",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the resolved plan without connecting",
    )
    arguments = parser.parse_args(argv)
    if not PAGE_PATTERN.fullmatch(arguments.page):
        parser.error("--page must be an absolute path such as /hub-export")
    if arguments.port is not None and not 1024 <= arguments.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        target = resolve_target(arguments.host)
        port = arguments.port or free_local_port()
        if arguments.dry_run:
            print(f"Host: {target.host}")
            print(f"URL: {target.url(arguments.page)}")
            print(f"Direct (not tunnelled): {target.keycloak}")
            print(f"Tunnel: {shlex.join(ssh_tunnel_command(target.host, port))}")
            print(f"Browser profile: {profile_directory(target.host)}")
            return 0
        if not arguments.no_browser and shutil.which("firefox") is None:
            raise TunnelError("firefox is not on PATH; install it or use --no-browser")
        print(f"Checking {target.host} over SSH (read-only):")
        report_preflight(target, *remote_preflight(target))
        return run_session(target, arguments.page, port, not arguments.no_browser)
    except TunnelError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
