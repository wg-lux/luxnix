{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.cli.shells;
in
{
  options.cli.shells.shared = with types; {
    enable = mkBoolOpt true "enable shared shell aliases";
  };

  config = mkIf (cfg.zsh.enable && cfg.shared.enable) {
    programs.zsh.shellAliases = {
      ls = "eza";
      ll = "eza -l";
      la = "eza -la";
      cd = "z";
      cdi = "zi";
      cp = "xcp";
      l = "eza --group --header --group-directories-first --long --git --all --binary --all --icons always";
      tree = "eza --tree";

      cleanup = "nix-collect-garbage -d";
      inspect-gcroots = "nix-store --gc --print-roots";
      optimize = "nix-store --optimize";
      journalctl-clear = "sudo journalctl --flush --rotate --vacuum-time=1s";

      # nix
      nhh = "nh home switch";
      nho = "nh os switch";
      nhu = "nh os --update";

      nd = "nix develop";
      nfu = "nix flake update";

      # other
      tldrf = "${pkgs.tldr}/bin/tldr --list | fzf --preview \"${pkgs.tldr}/bin/tldr {1} --color\" --preview-window=right,70% | xargs tldr";
    };
  };
}
