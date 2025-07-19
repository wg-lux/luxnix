# /default.nix
{ pkgs, ... }: {

cli.programs.git.allowedSigners = "";
cli.programs.git.enable = true;
cli.programs.git.email = "hamza.ukw@gmail.com";
desktops.plasma.enable = true;
luxnix.generic-settings.configurationPath = "dev/luxnix";
luxnix.generic-settings.language = "english";
luxnix.generic-settings.hostPlatform = "x86_64-linux";
roles.development.enable = true;
roles.video.enable = true;
roles.gpu.enable = true;
roles.social.enable = true;

home.stateVersion = "23.11";

}