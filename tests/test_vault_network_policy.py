"""Evaluate Vault address propagation without contacting Vault or reading secrets."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_vault_server_tls_and_client_pin_follow_inventory_host_selection() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = flake.inputs.nixpkgs.lib;
        evaluate = overrides:
          let
            configuration = host: (flake.nixosConfigurations.${host}.extendModules {
              modules = [ overrides ];
            }).config;
            server = configuration "gs-02";
            client = configuration "gc-06";
          in {
            listener = server.services.vault.address;
            inherit (server.luxnix.vault.server) apiAddress clusterAddress;
            sans = server.luxnix.vault.server.managedTls.ipAddresses;
            pins = lib.filterAttrs (_: names: builtins.elem "vault.endo-reg.net" names)
              client.networking.hosts;
            clientAddress = client.luxnix.vault.client.address;
            caFile = toString client.luxnix.vault.client.caCertFile;
            tlsEnabled = !server.services.vault.dev
              && server.services.vault.tlsCertFile != null;
            hostSelectionValid = !(builtins.any (assertion: !assertion.assertion
              && lib.hasPrefix "An inventory-managed Vault server" assertion.message)
              server.assertions);
          };
      in {
        baseline = evaluate {};
        changedAddress = evaluate {
          luxnix.generic-settings.network.hosts.gs-02.ip-vpn =
            lib.mkForce "10.20.30.22";
        };
        changedHost = evaluate {
          luxnix.generic-settings.network = {
            serviceHosts.vault = lib.mkForce "s-04";
            hosts.s-04 = {
              ip-vpn = lib.mkForce "10.20.30.14";
              ip-local = lib.mkForce "192.168.50.14";
              network-cluster = lib.mkForce "vault-test";
            };
            hosts.gc-06.network-cluster = lib.mkForce "vault-test";
          };
        };
        missingHost = (builtins.tryEval (builtins.deepSeq (evaluate {
          luxnix.generic-settings.network.serviceHosts.vault =
            lib.mkForce "missing-vault-host";
        }) true)).success;
      }
    """
    result = subprocess.run(
        ["nix", "eval", "--json", "--impure", "--expr", expression],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    cases = json.loads(result.stdout)
    for case, address in (
        ("baseline", "172.16.255.22"),
        ("changedAddress", "10.20.30.22"),
        ("changedHost", "10.20.30.14"),
    ):
        actual = cases[case]
        assert actual["listener"] == f"{address}:8200"
        assert actual["apiAddress"] == f"https://{address}:8200"
        assert actual["clusterAddress"] == f"https://{address}:8201"
        assert actual["sans"] == [address]
        assert list(actual["pins"]) == [address]
        assert "vault.endo-reg.net" in actual["pins"][address]
        assert actual["clientAddress"] == "https://vault.endo-reg.net:8200"
        assert actual["caFile"] == "/etc/secrets/vault/hub-pki/vault-server-ca.pem"
        assert actual["tlsEnabled"]
        # Selecting a new endpoint routes clients there, but the old server must
        # reject activation until its server configuration moves with the policy.
        assert actual["hostSelectionValid"] is (case != "changedHost")
    assert cases["missingHost"] is False
