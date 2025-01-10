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
      (import ./luxnix.nix { inherit config pkgs lib; })

    ]++extraImports;

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

  services.ssh.enable=true;

  environment.systemPackages = with pkgs; [
    nmap
    libreoffice-qt6-fresh
    hunspell
    hunspellDicts.de_DE
    hunspellDicts.en_US
    pandoc
    blender
  ];


  luxnix.generic-settings.systemStateVersion = "23.11";
}
