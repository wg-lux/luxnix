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
  options.cli.shells.zsh = with types; {
    enable = mkBoolOpt true "enable zsh shell";
  };

  config = mkIf cfg.enable {
    #  programs.bash.bashrcExtra = ''
	  #     # exec zsh
    #  '';
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

      initExtra = ''
          eval "$(direnv hook zsh)"
      '';

      #TODO read shell aliases from .json file; 
      shellAliases = {
        ls = "eza";
        ll = "eza -l";
        la = "eza -la";
        cd = "z";
        cdi = "zi";
        cp = "xcp";
        # ping = "gping";
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

      #Extra local variables defined at the top of .zshrc.
      localVariables = {
        # ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE = "fg=8";
        # ZSH_AUTOSUGGEST_USE_ASYNC = "true";
        # ZSH_AUTOSUGGEST_USE_CACHE = "true";
        # ZSH_AUTOSUGGEST_CACHE_EXPIRY = "3600";
        # ZSH_AUTOSUGGEST_CACHE_SIZE = "1000";
        # ZSH_AUTOSUGGEST_CACHE_PURGE = "true";
        # ZSH_AUTOSUGGEST_CACHE_PURGE_INTERVAL = "3600";
        # ZSH_AUTOSUGGEST_CACHE_PURGE_SIZE = "1000";
      };
    };
  };
}
