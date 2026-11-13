{
  config,
  lib,
  options,
  ...
}:
let
  inherit (lib) mkOption types;
  access = (import ../../../../../lib/network-access { inherit lib; }).networkAccess;
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
          sshTunnel = mkOption {
            type = types.submodule {
              options.enable = mkOption {
                type = types.bool;
                default = false;
                description = ''
                  Let the admin SSH account forward connections to this host's
                  own lx-annotate virtual host on port 443 and to no other
                  destination. Operators then reach the browser UI through
                  `devenv shell lx-annotate-tunnel <host>`; Keycloak login,
                  TLS and the hub transfer mTLS gate are unchanged.
                '';
              };
            };
            default = { };
            description = "Operator SSH tunnel to the local browser UI.";
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
                  type = types.listOf access.cidr;
                  # Leaders serve the VPN subnet; followers only operators and leaders.
                  default =
                    if options ? luxnix.networkAccess then config.luxnix.networkAccess.serviceSources else [ ];
                  defaultText = lib.literalExpression "config.luxnix.networkAccess.serviceSources";
                  example = [ "172.16.255.0/24" ];
                  description = "VPN networks in CIDR notation allowed to reach the browser UI and API over TLS.";
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
