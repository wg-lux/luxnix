{
  lib,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.roles.development;
in {
  options.roles.development = {
    enable = mkBoolOpt false "Enable development configuration";
  };

  config = mkIf cfg.enable {
    roles.desktop.enable = true;

    cli = {

      programs = {
        db.enable = true;
        direnv.enable = true;
        eza.enable = true;
        fzf.enable = true;
        git.enable = true;
        htop.enable = true;
        modern-unix.enable = true;
        network-tools.enable = true;
        nix-index.enable = true;
        podman.enable = false;
        ssh.enable = true;
        starship.enable = true;
        yazi.enable = true;
        zoxide.enable = true;
      };
    };
  };
}
