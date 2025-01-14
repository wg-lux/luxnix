{
  pkgs,
  config,
  lib,
  ...
}:
with lib; let
  cfg = config.roles.social;
in {
  options.roles.social = {
    enable = mkEnableOption "Enable social suite";
  };

  config = mkIf cfg.enable {
    programs = {
      # shotwell.enable = true;
    };
  };
}
