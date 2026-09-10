{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.cli.shells.zsh;
in
{
  options.cli.shells.zsh = with types; {
    enable = mkBoolOpt true "enable zsh shell";
  };

  config = mkIf cfg.enable {
    programs.zsh = {
      enable = true;
      autosuggestion.enable = true;
      syntaxHighlighting.enable = true;

      oh-my-zsh = {
        enable = true;
        package = pkgs.oh-my-zsh;
        plugins = [
          "git"
          "npm"
          "history"
          "node"
          "rust"
          "deno"
        ];
      };

      shellAliases = {
        show-auth-keys = "for f in /etc/ssh/authorized_keys.d/*; do echo \$f; cat \$f; done";
        lx-monitor = "scripts/monitor-lx-annotate-pipeline.sh --follow";
      };
    };
  };
}
