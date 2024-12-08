{
  config,
  lib,
  ...
}:
with lib; let
  cfg = config.services.luxnix.tailscale;
in {
  options.services.luxnix.tailscale = {
    enable = mkEnableOption "Enable tailscale";
  };

  config = mkIf cfg.enable {
    services.tailscale.enable = true;
  };
}
