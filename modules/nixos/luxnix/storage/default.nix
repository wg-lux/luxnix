{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.luxnix.storage;

  # luxnix persisting default mountpoint

in
{

  options.luxnix.storage = {
    enable = mkEnableOption "Enable Storage related settings for LuxNix systems";
    luxnix_storage_persisting_mountpoint = mkOption {
      type = types.path;
    };
  };

  config = mkIf cfg.enable {
      # add package smartmontools
      environment.systemPackages = with pkgs; [
        smartmontools
      ];

  };
}
