{ config,
  pkgs,
  lib,
  modulesPath,
  ...
}@inputs: 
  let
    extraImports = [ ];

  in
{

  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
    (import ./roles.nix {inherit config pkgs; })
    (import ./endoreg.nix { inherit config pkgs; })
    (import ./services.nix { inherit config pkgs lib; })
    (import ./luxnix.nix { inherit config pkgs; })

  ]++extraImports;

  hardware.graphics = {
    enable = true;
    # drivers = lib.mkForce 10 [ "ast" ]; # ASPEED Graphics Driver
  };

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };


  luxnix.generic-settings.systemStateVersion = "24.11";
}
