from pathlib import Path

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
