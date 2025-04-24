{...}:{}
# {
#   config,
#   lib,
#   ...
# }:
# #CHANGEME Set up traefik
# with lib; 
# with lib.luxnix; let
#   cfg = config.services.luxnix.traefik;
# in {
#   options.services.luxnix.traefik = {
#     enable = mkBoolOpt false "Enable traefik";
#   };

#   config = mkIf cfg.enable {
#     # allow firewall

#     systemd.tmpfiles.rules = [
#       "d /etc/traefik 0700 admin users -" 
#     ];
# ######




# #######
#     # systemd.services.traefik = {
#     #   environment = {
#     #     # CF_API_EMAIL = "hello@haseebmajid.dev";
#     #   };
#     #   serviceConfig = {
#     #     # EnvironmentFile = [config.sops.secrets.cloudflare_api_key.path];
#     #   };
#     # };

#     # sops.secrets.cloudflare_api_key = {
#     #   sopsFile = ../secrets.yaml;
#     # };


#     # systemd.services.traefik.restartIfChanged = true;
#     # systemd.services.traefik.wantedBy = [ "multi-user.target" ];


#     # services = {
#     #   # tailscale.permitCertUid = "traefik";

#     #   traefik = {
#     #     enable = true;

#     #     staticConfigOptions = {
#     #       log = {
#     #         level = "INFO";
#     #         filePath = "/var/log/traefik.log";
#     #         format = "json";
#     #         noColor = false;
#     #         maxSize = 100;
#     #         compress = true;
#     #       };

#     #       metrics = {
#     #         prometheus = {};
#     #       };

#     #       # tracing = {};

#     #       accessLog = {
#     #         addInternals = true;
#     #         filePath = "/var/log/traefik-access.log";
#     #         bufferingSize = 100;
#     #         fields = {
#     #           names = {
#     #             StartUTC = "drop";
#     #           };
#     #         };
#     #         filters = {
#     #           statusCodes = [
#     #             "204-299"
#     #             "400-499"
#     #             "500-599"
#     #           ];
#     #         };
#     #       };
#     #       api = {
#     #         dashboard = true;
#     #       };

#     #       # certificatesResolvers = {
#     #       #   tailscale.tailscale = {};
#     #       #   letsencrypt = {
#     #       #     acme = {
#     #       #       email = "hello@haseebmajid.dev";
#     #       #       storage = "/var/lib/traefik/cert.json";
#     #       #       dnsChallenge = {
#     #       #         provider = "cloudflare";
#     #       #       };
#     #       #     };
#     #       #   };
#     #       # };
#     #       entryPoints.redis = {
#     #         address = "0.0.0.0:6381";
#     #       };
#     #       entryPoints.web = {
#     #         address = "0.0.0.0:80";
#     #         http.redirections.entryPoint = {
#     #           to = "websecure";
#     #           scheme = "https";
#     #           permanent = true;
#     #         };
#     #       };
#     #       entryPoints.websecure = {
#     #         address = "0.0.0.0:443";
#     #         http.tls = {
#     #           certResolver = "letsencrypt";
#     #           domains = [
#     #             {
#     #               main = "endo-reg.net";
#     #               sans = ["*.endo-reg.net"];
#     #             }
#     #           ];
#     #         };
#     #       };
#     #     };

#         # dynamicConfigOptions
#       };
#     # };
#   # };
# }
