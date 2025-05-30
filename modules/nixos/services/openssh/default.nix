{
  config,
  lib,
  ...
}:
#CHANGEME 
with lib;
with lib.luxnix; let
  cfg = config.services.ssh;
in {
  options.services.ssh = with types; {
    enable = mkBoolOpt false "Enable ssh";
    authorizedKeys = mkOpt (listOf str) [] "The public keys to grant access to connect as admin.";
  };

  config = mkIf cfg.enable {
    services.openssh = {
      enable = true;
      ports = [22];

      settings = { #TODO LIMIT TO vpn access
        PasswordAuthentication = false;
        StreamLocalBindUnlink = "yes";
        GatewayPorts = "clientspecified";
      };
    };
    users.users = {
      ${config.user.admin.name}.openssh.authorizedKeys.keys = cfg.authorizedKeys;
    };
  };
}
