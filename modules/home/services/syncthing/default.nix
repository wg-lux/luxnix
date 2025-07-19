{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.syncthing;
in {
  options.services.luxnix.syncthing = {
    enable = mkBoolOpt false "Enable syncthing service";

    # tray = {
    #   enable = mkEnableOption "Enable syncthing tray";
    # };

    extraFlags = mkOption {
      type = types.listOf types.str;
      default = ["--gui-address=127.0.0.1:8384"];
      description = "Extra options to pass to syncthing";
    };
  };

  config = mkIf cfg.enable {
    services.syncthing = {
      enable = false; #TODO REACTIVATE LATER
      tray.enable = true;
      extraOptions = ["--gui-address=127.0.0.1:8384"];
    };
  };
}
