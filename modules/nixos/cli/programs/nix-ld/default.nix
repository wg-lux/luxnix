{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.nix-ld;
in {
  options.cli.programs.nix-ld = with types; {
    enable = mkBoolOpt true "Whether or not to enable nix-ld.";
  };

  config = mkIf cfg.enable {
    programs.nix-ld.enable = true;
  };
}
