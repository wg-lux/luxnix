# /default.nix
{ pkgs, ... }: {

luxnix.generic-settings.enable = true;
luxnix.generic-settings.hostPlatform = "x86_64-linux";

home.stateVersion = "23.11";

}