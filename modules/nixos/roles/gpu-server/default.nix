{
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.gpu-server;
in
{
  options.roles.gpu-server = {
    enable = mkBoolOpt false ''
      Enable gpu server configuration.
      Enables roles:
      - base-server
      - aglnet.client
    '';
  };

  config = mkIf cfg.enable {
    roles = {
      aglnet.client.enable = true;
      base-server.enable = true;
    };
  };
}
