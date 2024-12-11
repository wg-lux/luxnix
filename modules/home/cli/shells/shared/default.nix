{
  pkgs,
  lib,
  config,
  host,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.shells.zsh;
in {
  options.cli.shells.shared = with types; {
    enable = mkBoolOpt true "set shared shell options";
  };

  config = mkIf cfg.enable {
    programs.zsh = {
      enable = true;
      autosuggestion.enable = true;
      shellAliases = {
        ls = "eza";
        ll = "eza -l";
        la = "eza -la";
        cd = "z";
        cdi = "zi";
        cp = "xcp";
        ping = "gping";
        l = "eza --group --header --group-directories-first --long --git --all --binary --all --icons always";
        tree = "eza --tree";
        # sudo = "sudo -E -s";

        cleanup = "nix-collect-garbage -d";
        cleanup-roots = "sudo rm /nix/var/nix/gcroots/auto/*";
        optimize = "nix-store --optimize";
        journalctl-clear = "sudo journalctl --flush --rotate --vacuum-time=1s";

         # nix
        nhh = "nh home switch";
        nho = "nh os switch";
        nhu = "nh os --update";

        nd = "nix develop";
        nfu = "nix flake update";
        hms = "home-manager switch --flake ~/luxnix#${config.luxnix.user.admin.name}@${host}";
        nrs = "sudo nixos-rebuild switch --flake ~/luxnix#${host}";

        # other
        tldrf = "${pkgs.tldr}/bin/tldr --list | fzf --preview \"${pkgs.tldr}/bin/tldr {1} --color\" --preview-window=right,70% | xargs tldr";
        

      };
    };
  };
}
