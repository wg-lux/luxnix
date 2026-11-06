{ lib, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    remoteAccess = mkOption {
      type = types.submodule {
        options = {
          machines = mkOption {
            type = types.listOf (
              types.submodule {
                options = {
                  key = mkOption {
                    type = types.strMatching "[a-z0-9][a-z0-9-]{0,31}";
                    description = "Stable machine key shown to the selector.";
                  };
                  displayName = mkOption {
                    type = types.strMatching ".{1,60}";
                    description = "Operator-facing machine name.";
                  };
                  baseUrl = mkOption {
                    type = types.strMatching "https://[A-Za-z0-9.-]+(:[0-9]{1,5})?";
                    description = "Bare HTTPS origin of the machine's lx-annotate virtual host inside the LuxNix VPN.";
                  };
                  deploymentRole = mkOption {
                    type = types.enum [
                      "standalone"
                      "site_node"
                      "local_study_server"
                      "central_hub"
                    ];
                    description = "Deployment role of the target machine, displayed in the selector.";
                  };
                };
              }
            );
            default = [ ];
            description = ''
              LuxNix VPN machines offered in the lx-annotate remote-mode selector.
              Selecting one navigates the browser to that machine's own origin and
              Keycloak login; no API request is sent cross-origin.
            '';
          };
          restrictToVpn = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = ''
                    Serve the lx-annotate virtual host only to clients inside
                    allowedClientCidrs. Hub transfer locations keep their own
                    mTLS gate and are not affected.
                  '';
                };
                allowedClientCidrs = mkOption {
                  type = types.listOf (types.strMatching "[0-9]{1,3}(\\.[0-9]{1,3}){3}/[0-9]{1,2}");
                  default = [ ];
                  example = [ "172.16.255.0/24" ];
                  description = "IPv4 CIDRs of the LuxNix VPN allowed to reach the browser UI and API over TLS.";
                };
              };
            };
            default = { };
            description = "Restrict browser and API access to the LuxNix VPN.";
          };
        };
      };
      default = { };
      description = "Hub-mode remote access for authorized VPN laptops over TLS.";
    };
  };
}
