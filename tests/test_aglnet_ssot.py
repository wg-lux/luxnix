"""Evaluate VPN defaults and overrides without starting network services."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_vpn_routes_dns_and_client_filters_follow_shared_inputs() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = flake.inputs.nixpkgs.lib.extend (_: _: { luxnix = {}; });
        evaluate = role: overrides: (lib.evalModules {
          specialArgs.pkgs.openvpn = "/unused-openvpn";
          modules = [
            ./modules/nixos/roles/aglnet/host/default.nix
            ./modules/nixos/roles/aglnet/client/default.nix
            ./modules/nixos/luxnix/generic-settings/network/default.nix
            ({ lib, ... }: {
              options = builtins.listToAttrs (map (name: {
                inherit name;
                value = lib.mkOption { type = lib.types.attrs; };
              }) [ "networking" "services" "environment" "systemd" ]);
              config = {
                networking.hostName = "client";
                roles.aglnet.${role}.enable = true;
                luxnix.generic-settings.network.hosts = {
                  s-01.ip-vpn = "172.16.255.1";
                  s-02.ip-vpn = "172.16.255.12";
                  moved.ip-vpn = "10.42.0.9";
                };
              };
            })
            overrides
          ];
        }).config;
        changed = {
          roles.aglnet.host = {
            subnet = "10.42.0.0";
            subnetIntern = "255.255.0.0";
            localDomain = "test.intern";
          };
          luxnix.generic-settings.network.serviceHosts = {
            openvpn = "moved";
            nginx = "moved";
          };
        };
        select = c: {
          vpn = c.services.openvpn.servers.aglnet.config;
          dns = c.services.dnsmasq.settings or null;
          nameservers = c.networking.nameservers or [];
        };
      in {
        host = select (evaluate "host" {});
        client = select (evaluate "client" {});
        changedHost = select (evaluate "host" changed);
        changedClient = select (evaluate "client" changed);
        explicitClient = select (evaluate "client" {
          roles.aglnet.client = {
            subnet = "10.77.0.0";
            subnetIntern = "255.255.0.0";
            localDomain = "client.intern";
          };
        });
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--json", "--impure", "--expr", expression],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    cases = json.loads(result.stdout)
    for prefix, subnet, mask, address, proxy, domain in (
        (
            "",
            "172.16.255.0",
            "255.255.255.0",
            "172.16.255.1",
            "172.16.255.12",
            "endoreg.intern",
        ),
        (
            "changed",
            "10.42.0.0",
            "255.255.0.0",
            "10.42.0.9",
            "10.42.0.9",
            "test.intern",
        ),
    ):
        host = cases[prefix + "Host" if prefix else "host"]
        client = cases[prefix + "Client" if prefix else "client"]["vpn"]
        assert f"server {subnet} {mask}" in host["vpn"]
        assert host["vpn"].count(f'push "route {subnet} {mask}"') == 1
        assert host["nameservers"] == [address]
        assert host["dns"]["listen-address"] == address
        assert host["dns"]["domain"] == domain
        assert f'push "dhcp-option DNS {address}"' in host["vpn"]
        for endpoint in (address, proxy):
            assert f'push "route {endpoint} 255.255.255.255"' in host["vpn"]
            assert f'pull-filter accept "route {endpoint}"' in client
        assert f"route {subnet} {mask}" in client
        assert f'pull-filter accept "route {subnet}"' in client
        for option in ("DOMAIN", "DOMAIN-ROUTE", "DOMAIN-SEARCH"):
            assert f'push "dhcp-option {option} {domain}"' in host["vpn"]
            assert f'pull-filter accept "dhcp-option {option} {domain}"' in client
        assert "route-nopull" in client
        assert "remote-cert-tls server" in client
    assert "172.16.255." not in cases["changedHost"]["vpn"]
    assert "172.16.255." not in cases["changedClient"]["vpn"]
    explicit = cases["explicitClient"]["vpn"]
    assert "route 10.77.0.0 255.255.0.0" in explicit
    assert 'pull-filter accept "route 10.77.0.0"' in explicit
    assert 'pull-filter accept "dhcp-option DOMAIN client.intern"' in explicit
