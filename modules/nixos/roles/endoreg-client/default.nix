{
  lib,
  config,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.endoreg-client;
in {
  options.roles.endoreg-client = {
    enable = mkEnableOption "Enable endoreg client configuration";
  };

  config = mkIf cfg.enable {


    # Boot Modes:
    # TODO normal, maintenance
    # normal: no ssh access, can mount sensitive data
    # maintenance: ssh access, no sensitive data mountable
    # activate impermanence setup to make sure no sensitive data is left on the system

    # Services
    ## Anonymizer
    # Create anonymizer dirs #TODO move to service lx-anonymizer
    systemd.tmpfiles.rules = [
      "d /etc/lx-anonymizer/data 0700 admin users -" # TODO Change group from user to service or sth. when implemented
      "d /etc/lx-anonymizer/temp 0700 admin users -" 
    ];
  };
}
