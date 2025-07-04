# /default.nix
{ pkgs, ... }: {

cli.programs.git.allowedSigners = "";
cli.programs.git.enable = true;
cli.programs.git.email = "alice.ukw@gmail.com";
desktops.plasma.enable = "false";
services.luxnix.syncthing.enable = false;
luxnix.generic-settings.configurationPath = "dev/luxnix";
luxnix.generic-settings.language = "english";
luxnix.generic-settings.hostPlatform = "x86_64-linux";
roles.development.enable = false;
roles.video.enable = false;
roles.gpu.enable = true;
roles.social.enable = true;

home.stateVersion = "23.11";

}