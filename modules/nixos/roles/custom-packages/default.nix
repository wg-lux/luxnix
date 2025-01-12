{
  lib,
  pkgs,
  config,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.roles.custom-packages;

  p1 = with pkgs; [
    nmap
    libreoffice-qt6-fresh
    hunspell
    hunspellDicts.de_DE
    hunspellDicts.en_US
    pandoc
    blender
  ];

  customPackages = [] ++ p1;
in {
  options.roles.custom-packages = {
    enable = lib.mkBoolOpt false "Enable common configuration";

    p1 = lib.mkBoolOpt false "Add Packages of set 'p1' to custom packages";

  };


  config = mkIf cfg.enable {
    environment.systemPackages = customPackages;

    
  };
}
