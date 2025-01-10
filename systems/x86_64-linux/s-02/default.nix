{ config, pkgs, lib, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
    ./luxnix.nix
  ];

  user = {
    admin= {
    name= "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

roles = {
    base-server.enable= true;
    aglnet.client.enable= true;
    ssh-access.dev-01.enable= true;
    ssh-access.dev-01.idEd25519= ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK;
    };

  services = {

};
}