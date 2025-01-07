{
  lib,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.cli.terminals.tmux;
in {
  options.cli.terminals.tmux = {
    enable = mkBoolOpt false "Enable tmux configuration";
  };

  config = mkIf cfg.enable {
    programs.tmux = {
      enable=true;
      baseIndex = 1; # default is 0
      clock24 = true; # default is false
      mouse = true; # default is false
      newSession = false; # default is false; Automatically spawn a session if trying to attach and none are running.
      sensibleOnTop = true; # default is false
      shortcut = "a"; # default is "b"; Main shortcut is CTRL + b
      terminal = "screen-256color"; # default is "screen"
      tmuxinator.enable = true; # default is false
      tmuxp.enable = true; # default is false
    };
  };
}
