# /default.nix
{ pkgs, ... }: {

cli.programs.git.allowedSigners = " SHA256:nN5Ha+k2duMh/XZnKqa3Bs7jkUorUpsKzF+aqhTMMGg ";
cli.programs.git.enable = true;
cli.programs.git.email = "hamza.ukw@gmail.com";
cli.programs.git.userName = "Hamzaukw";
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