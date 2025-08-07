{
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.htop;
in {
  options.cli.programs.htop = with types; {
    enable = mkBoolOpt false "Whether or not to enable htop";
  };

  config = mkIf cfg.enable {
    # Backup existing htop config if it exists as a file (not directory)
    home.activation.backupHtopConfig = lib.hm.dag.entryBefore ["checkLinkTargets"] ''
      if [ -f "$HOME/.config/htop" ] && [ ! -d "$HOME/.config/htop" ]; then
        $DRY_RUN_CMD mv "$HOME/.config/htop" "$HOME/.config/htop.backup.$(date +%Y%m%d-%H%M%S)" || true
        echo "Backed up existing htop config file to avoid conflict with Home Manager"
      fi
    '';

    programs.htop = {
      enable = true;
      settings = {
        hide_userland_threads = 1;
        highlight_base_name = 1;
        show_cpu_temperature = 1;
        show_program_path = 0;
      };
    };
  };
}
