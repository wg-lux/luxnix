import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.yaml import load_unique_yaml_file

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_network_cluster_routing_requires_explicit_membership() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        lib = flake.inputs.nixpkgs.lib.extend (_: _: { luxnix = {}; });
        evaluate = own: remote: (lib.evalModules {
          modules = [
            ./modules/nixos/luxnix/generic-settings/network/default.nix
            ({ lib, ... }: {
              options.networking = lib.mkOption { type = lib.types.attrs; };
              config.networking.hostName = "client";
              config.luxnix.generic-settings.network.hosts = {
                client = { ip-vpn = "10.0.0.1"; } // own;
                peer = {
                  ip-vpn = "10.0.0.2";
                  ip-local = "192.168.1.2";
                } // remote;
              };
            })
          ];
        }).config.networking.hosts;
      in {
        omitted = evaluate {} {};
        unknown = evaluate { network-cluster = null; } { network-cluster = null; };
        oneKnown = evaluate { network-cluster = "LAN"; } {};
        different = evaluate { network-cluster = "A"; } { network-cluster = "B"; };
        matching = evaluate { network-cluster = "LAN"; } { network-cluster = "LAN"; };
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
    for case in ("omitted", "unknown", "oneKnown", "different"):
        assert cases[case]["10.0.0.2"] == ["peer"]
        assert "192.168.1.2" not in cases[case]
    assert cases["matching"]["192.168.1.2"] == ["peer"]
    assert "10.0.0.2" not in cases["matching"]


def test_gc06_is_targetable_by_managed_deployment() -> None:
    inventory = AnsibleInventory.load_from_hosts_ini(
        REPO_ROOT / "ansible/inventory/hosts.ini", subnet="172.16.255."
    )
    host = next(host for host in inventory.all if host.hostname == "gc-06")
    assert "managed" in host.ansible_group_names


def test_keycloak_dependency_uses_the_configured_vpn_service_name() -> None:
    keycloak = (REPO_ROOT / "modules/nixos/roles/keycloak_host/default.nix").read_text(
        encoding="utf-8"
    )
    cheatsheet = (REPO_ROOT / "LxCheatsheet.md").read_text(encoding="utf-8")

    assert (
        'vpnServiceName = "openvpn-${config.roles.aglnet.client.networkName}.service";'
        in keycloak
    )
    assert keycloak.count("= keycloakServiceDependencies;") == 2
    assert "openvpn-aglNet.service" not in keycloak
    assert "openvpn-aglnet.service" in cheatsheet


def test_keycloak_bind_address_uses_the_central_service_host_mapping() -> None:
    keycloak = (REPO_ROOT / "modules/nixos/roles/keycloak_host/default.nix").read_text(
        encoding="utf-8"
    )
    network = (
        REPO_ROOT / "modules/nixos/luxnix/generic-settings/network/default.nix"
    ).read_text(encoding="utf-8")

    assert 'default = getServiceVpnIp "keycloak";' in network
    assert "http-host = conf.vpnIp;" in keycloak
    assert "network.hosts.s-02.ip-vpn" not in keycloak
    assert "vpnIp = config.luxnix.generic-settings.network.hosts." not in keycloak


def test_wg_lux_mcp_is_enabled_for_every_active_machine() -> None:
    shared = load_unique_yaml_file(
        REPO_ROOT / "ansible/inventory/group_vars/all/30-nix.yml"
    )
    assert shared["group_services"]["wg-lux-mcp.enable"] == "true"

    inventory = AnsibleInventory.load_from_hosts_ini(
        REPO_ROOT / "ansible/inventory/hosts.ini",
        subnet="172.16.255.",
    )
    active_hosts = {
        host.hostname
        for host in inventory.all
        if "active_clients" in host.ansible_group_names
    }
    assert active_hosts

    for hostname in active_hosts:
        generated = (
            REPO_ROOT / f"systems/x86_64-linux/{hostname}/default.nix"
        ).read_text(encoding="utf-8")
        assert "services.wg-lux-mcp.enable = true;" in generated


def test_wg_lux_mcp_uses_a_machine_local_dns_override() -> None:
    module = (REPO_ROOT / "wg-lux-mcp/nixos/wg-lux-mcp.nix").read_text(encoding="utf-8")

    assert 'default = "wg-lux-mcp.local";' in module
    assert 'networking.hosts."127.0.0.1" = [ cfg.hostname ];' in module
    assert "WG_LUX_MCP_PUBLIC_HOST = cfg.hostname;" in module
    assert 'default = "127.0.0.1";' in module
    assert "services.luxnix.lxSsl" in module
    assert "extraDnsNames = lib.mkAfter [ cfg.hostname ];" in module
    assert "forceSSL = true;" in module
    assert 'proxyPass = "http://${cfg.host}:${toString cfg.port}";' in module
    assert "Require Keycloak OAuth access tokens" in module
    assert 'default = "wg-lux-mcp";' in module
    assert 'default = [ "openid" ];' in module
    assert "WG_LUX_MCP_OAUTH_ENABLED" in module
    assert "WG_LUX_MCP_OAUTH_ISSUER_URL" in module
    assert "wg-lux-features.enable = true;" in module
    assert "WG_LUX_FEATURE_PROVIDER_REGISTRY" in module
    assert "WG_LUX_FEATURE_STATE_ROOT" in module
    assert "config.services.wg-lux-features.registryPath" in module
    assert "config.services.wg-lux-features.stateRoot" in module


def test_lx_annotate_local_advertises_its_https_vhost() -> None:
    options = (
        REPO_ROOT / "modules/nixos/services/lx-annotate-local/options/django.nix"
    ).read_text(encoding="utf-8")

    assert 'hostname = "lx-annotate.local";' in options
    assert 'baseUrl = "https://lx-annotate.local";' in options
    assert 'httpProtocol = "https";' in options
    assert "useHttps = true;" in options


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_shared_application_endpoints_follow_network_policy() -> None:
    expression = r"""
      let
        flake = builtins.getFlake ("git+file://" + builtins.toString ./.);
        evaluate = name: changed:
          let
            host = flake.nixosConfigurations.${name};
            c = (host.extendModules {
              modules = flake.inputs.nixpkgs.lib.optional changed ({ lib, ... }: {
                luxnix.generic-settings.network = {
                  hosts.gs-02.ip-vpn = lib.mkForce "10.20.30.22";
                  hosts.s-04.ip-vpn = lib.mkForce "10.20.30.14";
                  psqlMain.port = lib.mkForce 5544;
                  redis.port = 6390;
                };
              });
            }).config;
            app = c.services.luxnix.lxAnnotateLocal;
          in {
            database = { inherit (app.database) host port ownership; };
            aiDatabasePort = c.services.luxnix.lxAiLocal.database.port;
            broker = app.runtime.externalServices.redisUrl;
            postgres = {
              port = c.services.postgresql.settings.port;
              setupPort = c.systemd.services.postgres-endoreg-setup.environment.PGPORT;
            };
            databaseFailures = map (a: a.message) (builtins.filter
              (a: !a.assertion && (
                flake.inputs.nixpkgs.lib.hasPrefix "LX-Annotate database" a.message
                || flake.inputs.nixpkgs.lib.hasPrefix
                  "LX-Annotate managed-local" a.message
                || flake.inputs.nixpkgs.lib.hasPrefix "PostgreSQL shared" a.message
              )) c.assertions);
            redis = if name == "s-04" then {
              inherit (c.services.redis.servers.main) bind port;
            } else null;
            sshUnchanged =
              c.services.openssh.settings == host.config.services.openssh.settings
              && c.services.openssh.ports == host.config.services.openssh.ports;
          };
      in builtins.listToAttrs (map (name: {
        inherit name;
        value = { before = evaluate name false; after = evaluate name true; };
      }) [ "gs-01" "s-04" "gs-02" "gc-10" ])
    """
    result = subprocess.run(
        ["nix", "eval", "--json", "--impure", "--expr", expression],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    cases = json.loads(result.stdout)
    for name in ("gs-01", "s-04"):
        assert cases[name]["before"]["database"] == {
            "host": "172.16.255.22",
            "port": 5432,
            "ownership": "external",
        }
        assert cases[name]["before"]["broker"] == "redis://172.16.255.14:6380/1"
        assert cases[name]["after"]["database"] == {
            "host": "10.20.30.22",
            "port": 5544,
            "ownership": "external",
        }
        assert cases[name]["after"]["broker"] == "redis://10.20.30.14:6390/1"
        assert cases[name]["after"]["sshUnchanged"]
    assert cases["s-04"]["after"]["redis"] == {"bind": "10.20.30.14", "port": 6390}
    # The shared owner keeps local ownership/address, but follows its listener.
    assert cases["gs-02"]["after"]["database"] == {
        "host": "127.0.0.1",
        "port": 5544,
        "ownership": "local",
    }
    assert cases["gs-02"]["after"]["postgres"] == {"port": 5544, "setupPort": "5544"}
    assert cases["gs-02"]["after"]["aiDatabasePort"] == 5544
    assert cases["gs-02"]["before"]["broker"] == cases["gs-02"]["after"]["broker"]
    # An unrelated local database must not inherit the shared server's port.
    assert cases["gc-10"]["before"] == cases["gc-10"]["after"]
    for case in cases.values():
        assert (
            case["before"]["databaseFailures"]
            == case["after"]["databaseFailures"]
            == []
        )


@pytest.mark.skipif(shutil.which("nix") is None, reason="Nix evaluation required")
def test_postgres_listener_overrides_keep_firewall_and_policy_consistent() -> None:
    expression = r"""
      let
        f = builtins.getFlake ("git+file://" + builtins.toString ./.);
        evaluate = name: let
          c = (f.nixosConfigurations.${name}.extendModules {
            modules = [ ({ lib, ... }: {
              roles.postgres.main.enable = true;
              services.postgresql.settings.port = lib.mkForce 5545;
            }) ];
          }).config;
        in {
          firewall = c.networking.firewall.allowedTCPPorts;
          setupPort = c.systemd.services.postgres-endoreg-setup.environment.PGPORT;
          sharedPortValid = (builtins.filter (a: !a.assertion
            && f.inputs.nixpkgs.lib.hasPrefix "PostgreSQL shared" a.message)
            c.assertions) == [];
        };
      in { shared = evaluate "gs-02"; independent = evaluate "gc-10"; }
    """
    result = subprocess.run(
        ["nix", "eval", "--json", "--impure", "--expr", expression],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    cases = json.loads(result.stdout)
    for case in cases.values():
        assert 5545 in case["firewall"]
        assert 5432 not in case["firewall"]
        assert case["setupPort"] == "5545"
    assert cases["shared"]["sharedPortValid"] is False
    assert cases["independent"]["sharedPortValid"] is True
