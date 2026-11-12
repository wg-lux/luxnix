{
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.base-server;
in
{
  options.roles.base-server = {
    enable = mkEnableOption "Enable base server configuration";
  };

  config = mkIf cfg.enable {
    # Servers and the central hub serve the VPN; this outranks the follower
    # tier that endoreg-client sets on hub hosts.
    luxnix.networkAccess.tier = lib.luxnix.networkAccess.mkTierDefault "leader";

    roles = {
      common.enable = true;
      custom-packages.baseDevelopment = true;
    };

    services = {
      luxnix.avahi.enable = false;
    };
  };
}
