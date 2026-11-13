"""Role-derived client allowlists and the shared CIDR validator."""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLAKE = f'builtins.getFlake "git+file://{ROOT}"'


@lru_cache(maxsize=None)
def _eval(expression: str) -> Any:
    result = subprocess.run(
        ["nix", "eval", "--impure", "--json", "--expr", expression],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _validator(values: list[str]) -> list[bool]:
    return _eval(
        f"""
        let lib = ({FLAKE}).inputs.nixpkgs.lib;
            access = (import ./lib/network-access {{ inherit lib; }}).networkAccess;
        in map access.isAllowlistCidr (builtins.fromJSON ''{json.dumps(values)}'')
        """
    )


ACCEPTED = [
    "172.16.255.0/24",
    "172.16.255.106/32",
    "192.168.0.0/16",
    "2001:db8::/48",
    "::1/128",
    "2001:db8:0:ff00::/56",
]
REJECTED = [
    "0.0.0.0/0",  # whole address space
    "10.0.0.0/8",  # broader than a site network
    "::/0",
    "172.16.255.5/24",  # host bits set
    "2001:db8::1/64",
    "256.1.1.1/32",
    "010.1.1.1/32",  # ambiguous leading zero
    "1.2.3.4",  # bare address; use hostCidr
    "1.2.3.4/33",
    "1::2::3/128",
    "fe80::1%eth0/128",
]


def test_validator_accepts_site_networks_and_rejects_broad_or_malformed() -> None:
    assert _validator(ACCEPTED) == [True] * len(ACCEPTED)
    assert _validator(REJECTED) == [False] * len(REJECTED)


def _host(name: str, module: str = "{ }") -> dict[str, Any]:
    return _eval(
        f"""
        let
          h = ({FLAKE}).nixosConfigurations.{name}.extendModules {{
            modules = [ ({{ lib, ... }}: {module}) ];
          }};
          c = h.config;
          n = c.luxnix.networkAccess;
        in {{
          inherit (n) tier managementSources serviceSources earlyBootSources;
          unlock = c.luxnix.storage.operatorUnlocked.remoteUnlock.allowedSources;
          vpnClients = c.services.luxnix.lxAnnotateLocal.remoteAccess.restrictToVpn.allowedClientCidrs;
        }}
        """
    )


def test_roles_select_tier_and_leader_outranks_client_role() -> None:
    follower = _host("gc-09")
    hub = _host("gs-02")  # carries both base-server and endoreg-client

    assert follower["tier"] == "follower"
    assert hub["tier"] == "leader"
    assert hub["serviceSources"] == ["172.16.255.0/24"]
    assert follower["serviceSources"] == follower["managementSources"]
    assert hub["vpnClients"] == hub["serviceSources"]
    assert follower["vpnClients"] == follower["serviceSources"]


def test_follower_trusts_leaders_and_leader_ignores_them() -> None:
    module = '{ luxnix.networkAccess.leaderHosts = [ "gs-02" ]; }'

    assert "172.16.255.22/32" in _host("gc-09", module)["managementSources"]
    assert "172.16.255.22/32" not in _host("s-04", module)["managementSources"]


def test_early_boot_sources_use_lan_addresses_in_the_same_cluster_only() -> None:
    # gs-01 and gs-02 share cluster L2 with LAN addresses; gc-09 has no cluster.
    module = '{ luxnix.networkAccess.operatorHosts = [ "gs-02" ]; }'
    same_cluster = _host("gs-01", module)
    no_cluster = _host("gc-09", module)

    assert same_cluster["earlyBootSources"] == ["192.168.0.56/32"]
    assert same_cluster["unlock"] == ["192.168.0.56/32"]
    assert no_cluster["earlyBootSources"] == []


def test_unknown_trusted_host_fails_loudly() -> None:
    with pytest.raises(AssertionError, match="not in luxnix.generic-settings.network.hosts"):
        _host("gc-09", '{ luxnix.networkAccess.operatorHosts = [ "no-such-host" ]; }')


def test_overly_broad_override_is_rejected_by_type() -> None:
    with pytest.raises(AssertionError, match="allowlistCidr|no host bits set"):
        _host("gs-02", '{ luxnix.networkAccess.extraManagementSources = [ "0.0.0.0/0" ]; }')
