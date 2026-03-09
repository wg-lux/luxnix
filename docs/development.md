# Development

## General Settings Module

LuxNix has a general settings module.
The option for it is enabled by default and has default values. It can be referenced in other parts of the configuration like this:

'variableToSet = config.luxnix.generic-settings.configurationPath' which is defined as option:

```
options.luxnix.generic-settings = {
    enable = mkEnableOption "Enable generic settings";
  
    configurationPath = mkOption {
      type = types.path;
      default = "/home/${config.user.admin.name}/luxnix/";
      description = ''
        Path to the luxnix directory.
      '';
    };
};
```

## Installing Packages

Use this workflow when adding command-line tools for Endoreg client machines.

1. For tools that should exist on all Endoreg clients, add them in:
   - `modules/nixos/roles/custom-packages/default.nix`
2. Prefer placing general utilities in the `baseDevelopment` package list.
3. Keep service modules focused on service runtime dependencies only.
4. For one host only, place packages in:
   - `systems/x86_64-linux/<host>/default.nix`
5. Apply and test:
   - `sudo nixos-rebuild switch --flake .#<host>`
   - `which rg && which duf && which dysk`

## Git

Setting up git configuration for your profile at luxnix/homes/x86_64-linux/admin@gc-02/default.nix:

```
{pkgs, ...}: {
  # cli.programs.git.allowedSigners = ; #TODO

  cli.programs.git = {
    enable = true;
    userName = "CHANGE_ME";
    email = "CHANGE_ME@CHANGEMAIL.com";
    allowedSigners = " SHA256:yourkey";
  };

  desktops = {
    plasma = {
      enable = true;
    };
  };

  services.luxnix = {
    # syncthing.enable = false;
  };

  roles = {
    development.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
