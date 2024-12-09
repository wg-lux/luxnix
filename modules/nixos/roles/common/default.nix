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


    cli.programs = {
      nh.enable = true;
      nix-ld.enable = true;
    };


    

    security = {
      sops.enable = true;
    };

    programs = {
      zsh.enable = true;
    };

    system = {
      nix.enable = true;
      boot.enable = true;
      boot.secureBoot = false;
      locale.enable = true;
      boot.plymouth = true;
    };
  };
}
