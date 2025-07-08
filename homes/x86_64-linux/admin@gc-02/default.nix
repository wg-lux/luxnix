# /default.nix
{ pkgs, ... }: {

cli.programs.git.allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
cli.programs.git.enable = true;
cli.programs.git.email = "maxhild10@gmail.com";
cli.programs.git.userName = "maxhild";
desktops.plasma.enable = true;
luxnix.generic-settings.configurationPath = "dev/luxnix";
luxnix.generic-settings.language = "english";
luxnix.generic-settings.enable = true;
luxnix.generic-settings.hostPlatform = "x86_64-linux";
roles.development.enable = true;
roles.video.enable = true;
roles.gpu.enable = true;
roles.social.enable = true;

home.stateVersion = "23.11";

}