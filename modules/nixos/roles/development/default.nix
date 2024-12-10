{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.devUser;
in {
  options.roles.devUser = {
    enable = mkEnableOption "Enable Dev users";
  };

  config = mkIf cfg.enable {
    #user = {
    #  name = "dev01";
    #  initialPassword = "1";
    #};
########
    users.mutableUsers = false;
    users.users.dev01 =
    let 
    initialPassword = "1";
    name = "dev01";
    in
      {
        isNormalUser = true;
        initialPassword = "1";
        home = "/home/${name}";
        group = "users";

        extraGroups =
          [
            "wheel"
            "audio"
            "sound"
            "video"
            "networkmanager"
            "input"
            "tty"
            "podman"
            "kvm"
            "libvirtd"
          ];
      };
      
    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
    };
######
  };

}