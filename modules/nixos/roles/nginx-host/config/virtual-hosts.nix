{ lib ? <nixpkgs/lib> , ... }:
let
    base = import ./base.nix { inherit lib; };
    network = import ../../network/main.nix { inherit lib; };
    domains = network.domains;
    ips = network.ips;
    service-hosts = import ../../service-hosts.nix { inherit lib; };

    ssl-certificate-path = base.paths.ssl-certificate;
    ssl-certificate-key-path = base.paths.ssl-certificate-key;

    keycloak-host-vpn-ip = ips.clients."${service-hosts.keycloak}";

    intern-endoreg-net-extraConfig = ''
        allow 172.16.255.0/24; 
        deny all;
    '';


    virtual-hosts = {

        "keycloak-intern.endo-reg.net" = {
            forceSSL = true;
            sslCertificate = ssl-certificate-path;
            sslCertificateKey = ssl-certificate-key-path;

            locations."/" = {
                proxyPass = "http://${keycloak-host-vpn-ip}:${toString network.ports.keycloak.http}"; # TODO FIXME
                extraConfig = base.all-extraConfig + intern-endoreg-net-extraConfig;
            };
        };

        "${domains.keycloak}" = {
            forceSSL = true;
            sslCertificate = ssl-certificate-path;
            sslCertificateKey = ssl-certificate-key-path;

            locations."/" = {
                proxyPass = "http://${keycloak-host-vpn-ip}:${toString network.ports.keycloak.http}"; # TODO FIXME
                extraConfig = base.all-extraConfig;
            };
        };

        

    };

in virtual-hosts