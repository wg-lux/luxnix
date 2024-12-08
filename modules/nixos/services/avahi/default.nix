{
  lib,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.avahi;
in {
  # Direct file transfer between devices
  options.services.luxnix.avahi = {
    enable = mkBoolOpt false "Enable The avahi service";
  };

  config = mkIf cfg.enable {
    services.avahi = {
      enable = true;
      nssmdns4 = true;
      publish = {
        enable = true;
        addresses = true;
        domain = true;
        hinfo = true;
        userServices = true;
        workstation = true;
      };
    };
  };
}
