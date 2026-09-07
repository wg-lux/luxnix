from pathlib import Path

from lx_administration.models.ansible.inventory import AnsibleInventory
from lx_administration.yaml import load_unique_yaml_file

REPO_ROOT = Path(__file__).resolve().parents[1]


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
    module = (REPO_ROOT / "wg-lux-mcp/nixos/wg-lux-mcp.nix").read_text(
        encoding="utf-8"
    )

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
