{ lib ? <nixpkgs/lib> , ... }:
let

    service-users = import ../../service-users.nix { inherit lib; };
    service-hosts = import ../../service-hosts.nix { inherit lib; };
    paths = import ../../paths/nginx.nix { }; 

    network = import ../../network/main.nix { inherit lib; };
    ips = network.ips;

    hostnames = import ../../hostnames.nix { inherit lib; };

    hostname = "s-02";

    proxy_headers_hash_max_size = 512;
    proxy_headers_hash_bucket_size = 64;

    base = {
        hostname = hostname;
        raw-host = raw-host;
        recommendedGzipSettings = true;
        recommendedOptimisation = true;
        recommendedProxySettings = true;
        recommendedTlsSettings = true;
        domain = network.domains.keycloak;
        
        host-ip = network.ips.clients."${raw-host}";
        port = network.ports.nginx.aglnet;
        user = service-users.nginx.user.name;
        group = service-users.nginx.user.config.group;
        filemode-secret = "0400";
        paths = paths;

        all-extraConfig = ''
            proxy_headers_hash_bucket_size ${toString proxy_headers_hash_bucket_size};
            proxy_headers_hash_max_size ${toString proxy_headers_hash_max_size};
        '';
        
        intern-endoreg-net-extraConfig = ''
            allow ${ips.vpn-subnet};
            deny all;
        '';

        appendHttpConfig = ''
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_ssl_server_name on;
            proxy_pass_header Authorization;
        '';
        
    };


in base
