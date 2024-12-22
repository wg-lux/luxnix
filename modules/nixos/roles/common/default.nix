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
      parted
      cryptsetup
      lsof
      e2fsprogs
      nix-prefetch-scripts
    ];

    systemd.tmpfiles.rules = [
      "d /etc/user-passwords 0700 admin users -"
    ];

    roles.postgres.default.enable = true;

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
      command-not-found.enable = true;
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
