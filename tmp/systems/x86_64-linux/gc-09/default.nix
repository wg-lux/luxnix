{ config, pkgs, lib, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
  ];

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

  roles = {
    };

  services = {
    };

  luxnix = {
    traefik-host.enable = false;

    nvidia-prime = {
      enable = true;
      nvidiaBusId = "PCI:1:0:0";
    };

  };
}