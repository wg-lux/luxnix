{
  lib,
  pkgs,
  config,
  ...
}: let
  cfg = config.roles.common;
in {
  options.roles.common = {
    enable = lib.mkEnableOption "Enable common configuration";
  };

  config = lib.mkIf cfg.enable {
    browsers.firefox.enable = true;

    system = {
      nix.enable = true;
    };
    programs.zsh.enable = true;
    cli = {
      terminals.foot.enable = true;
      terminals.kitty.enable = true;
      shells.zsh.enable = true;
      shells.shared.enable = true;
    };
    programs = {
      guis.enable = true;
      tuis.enable = true;
    };

    security = {
      sops.enable = true;
    };

    # TODO: move this to a separate module
    home.packages = with pkgs; [
      keymapp

      src-cli
      optinix

      (hiPrio parallel)
      moreutils
      nvtopPackages.amd
      unzip
      gnupg

      showmethekey
    ];
  };
}
