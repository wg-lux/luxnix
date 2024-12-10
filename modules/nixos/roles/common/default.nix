{
  lib,
  pkgs,
  config,
  ...
}:
with lib; let
  cfg = config.roles.common;
in {
  options.roles.common = {
    enable = mkEnableOption "Enable common configuration";
  };

  

  config = mkIf cfg.enable {
      environment.systemPackages = with pkgs; [
      devenv
    ];
    hardware = {
      networking.enable = true;
       
      # EXPERIMENTAL
      graphics.enable = true;
    };

    services = {
      ssh.enable = true;
    };

    security = {
      sops.enable = true;
    };

    system = {
      nix.enable = true;
      boot.enable = true;
      locale.enable = true;
    };
  };
}
