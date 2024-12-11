{
  config,
  lib,
  ...
}:
with lib; let
  cfg = config.services.luxnix.syncthing;
in {
  options.services.luxnix.syncthing = {
    enable = mkBoolOpt false "Enable syncthing service";

    # tray = {
    #   enable = mkEnableOption "Enable syncthing tray";
    # };

    # extraOptions = mkOption {
    #   type = types.listOf types.str;
    #   default = ["--gui-address=127.0.0.1:8384"];
    #   description = "Extra options to pass to syncthing";
    # };
  };

  config = mkIf cfg.enable {
    # services.syncthing = {
    #   enable = true;
    #   tray.enable = true;
    #   extraOptions = ["--gui-address=127.0.0.1:8384"];
    # };
  };
}
