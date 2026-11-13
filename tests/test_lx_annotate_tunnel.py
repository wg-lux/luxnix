from __future__ import annotations

import importlib.util
import socket
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/lx-annotate-tunnel.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lx_annotate_tunnel", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tunnel = _load()


def _inventory(root: Path, host_services: str = "") -> Path:
    (root / "host_vars").mkdir(parents=True)
    (root / "group_vars/all").mkdir(parents=True)
    (root / "hosts.ini").write_text(
        "[all]\nnode-a ansible_host=10.0.0.1 # site\n\n[clients]\nnode-a\nghost\n",
        encoding="utf-8",
    )
    (root / "host_vars/node-a.yml").write_text(
        f"host_services:\n  other.option: '1'\n{host_services}", encoding="utf-8"
    )
    (root / "group_vars/all/30-nix.yml").write_text(
        "group_luxnix:\n"
        "  generic_settings.network.keycloak.domain: '\"login.example.org\"'\n",
        encoding="utf-8",
    )
    return root


def test_target_defaults_to_the_machine_local_name(tmp_path: Path) -> None:
    target = tunnel.resolve_target("node-a", _inventory(tmp_path))

    assert target.vhost == "lx-annotate.local"
    assert target.keycloak == "login.example.org"
    assert target.url("/hub-export") == "https://lx-annotate.local/hub-export"


def test_target_uses_the_host_specific_name(tmp_path: Path) -> None:
    root = _inventory(
        tmp_path,
        "  luxnix.lxAnnotateLocal.django.hostname: '\"node-a.intern\"'\n",
    )

    assert tunnel.resolve_target("node-a", root).vhost == "node-a.intern"


@pytest.mark.parametrize("host", ["ghost", "clients", "node-a;id"])
def test_only_addressed_inventory_hosts_are_accepted(tmp_path: Path, host: str) -> None:
    with pytest.raises(tunnel.TunnelError, match="not a host"):
        tunnel.resolve_target(host, _inventory(tmp_path))


def test_unsafe_configured_name_is_rejected(tmp_path: Path) -> None:
    root = _inventory(
        tmp_path,
        "  luxnix.lxAnnotateLocal.django.hostname: '\"a b; rm\"'\n",
    )

    with pytest.raises(tunnel.TunnelError, match="plain host name"):
        tunnel.resolve_target("node-a", root)


def test_tunnel_binds_loopback_and_fails_on_refused_forward() -> None:
    command = tunnel.ssh_tunnel_command("node-a", 4000)

    assert command[:5] == ["ssh", "-N", "-T", "-D", "127.0.0.1:4000"]
    assert "ExitOnForwardFailure=yes" in command
    assert command[-1] == "node-a"
    assert not any(option in command for option in ("-A", "-R", "-g"))


def test_profile_has_no_direct_route_to_the_application(tmp_path: Path) -> None:
    profile = tmp_path / "state/node-a"
    tunnel.prepare_profile(profile, 4000, "login.example.org")
    preferences = (profile / "user.js").read_text(encoding="utf-8")

    assert profile.stat().st_mode & 0o777 == 0o700
    assert 'user_pref("network.proxy.type", 1);' in preferences
    assert 'user_pref("network.proxy.socks_port", 4000);' in preferences
    assert 'user_pref("network.proxy.socks_remote_dns", true);' in preferences
    assert 'user_pref("network.proxy.failover_direct", false);' in preferences
    assert (
        'user_pref("network.proxy.no_proxies_on", "login.example.org");' in preferences
    )
    assert "lx-annotate" not in preferences


def test_fingerprint_is_absent_without_a_certificate() -> None:
    assert tunnel.certificate_fingerprint("") is None


def _socks_server(reply: bytes) -> tuple[int, list[bytes]]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    requests: list[bytes] = []

    def serve() -> None:
        connection, _ = server.accept()
        with connection, server:
            connection.recv(3)
            connection.sendall(b"\x05\x00")
            requests.append(connection.recv(64))
            connection.sendall(reply)

    threading.Thread(target=serve, daemon=True).start()
    return server.getsockname()[1], requests


def test_tunnel_check_requests_the_name_not_a_local_address() -> None:
    port, requests = _socks_server(b"\x05\x00\x00\x01" + bytes(6))

    tunnel.socks_connect_check(port, "lx-annotate.local")

    assert requests == [b"\x05\x01\x00\x03\x11lx-annotate.local\x01\xbb"]


@pytest.mark.parametrize("reply", [b"\x05\x02\x00\x01" + bytes(6), b""])
def test_refused_forward_names_the_missing_host_option(reply: bytes) -> None:
    port, _ = _socks_server(reply)

    with pytest.raises(tunnel.TunnelError, match="sshTunnel.enable"):
        tunnel.socks_connect_check(port, "lx-annotate.local")


def test_stopped_application_aborts_and_hub_outage_warns(capsys) -> None:
    target = tunnel.Target("node-a", "lx-annotate.local", "login.example.org")
    states = dict.fromkeys(tunnel.REQUIRED_UNITS + tunnel.HUB_UNITS, "active")

    tunnel.report_preflight(target, {**states, tunnel.HUB_UNITS[0]: "inactive"}, None)
    assert "hub transfer services are not active" in capsys.readouterr().err

    with pytest.raises(tunnel.TunnelError, match="nothing to open"):
        tunnel.report_preflight(
            target, {**states, "lx-annotate.service": "failed"}, None
        )


def test_dry_run_resolves_a_real_client_without_connecting(capsys) -> None:
    assert tunnel.main(["gc-05", "--hub-export", "--dry-run"]) == 0
    output = capsys.readouterr().out

    assert "URL: https://lx-annotate.local/hub-export" in output
    assert "172.16.255." not in SCRIPT.read_text(encoding="utf-8")
