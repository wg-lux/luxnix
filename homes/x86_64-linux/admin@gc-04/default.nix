# /default.nix
{ pkgs, ... }: {

cli.programs.git.allowedSigners = "";
cli.programs.git.enable = true;
desktops.plasma.enable = true;
luxnix.generic-settings.configurationPath = "lx-production";
luxnix.generic-settings.language = "english";
luxnix.generic-settings.enable = true;
luxnix.generic-settings.hostPlatform = "x86_64-linux";
roles.development.enable = true;
roles.video.enable = true;

home.stateVersion = "23.11";

}