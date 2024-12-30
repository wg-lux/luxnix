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

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };


  system.stateVersion = "23.11";
}
