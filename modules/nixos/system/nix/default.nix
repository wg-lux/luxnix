{ config
, lib
, ...
}:
#CHANGEME: Add agl admin
with lib;
with lib.luxnix; let
  cfg = config.system.nix;
  gs = config.luxnix.generic-settings;

  endoregServiceUserName = config.user.endoreg-service-user.name;

in
{
  options.system.nix = with types; {
    enable = mkBoolOpt false "Whether or not to manage nix configuration";
  };

  config = mkIf cfg.enable {
    nix = {
      settings = {
        trusted-users = [ "@wheel" "root" "admin" "${endoregServiceUserName}" ];
        auto-optimise-store = lib.mkDefault true;
        use-xdg-base-directories = true;
        experimental-features = [ "nix-command" "flakes" ];
        warn-dirty = false;
        system-features = [ "kvm" "big-parallel" "nixos-test" ];
      };

      # flake-utils-plus
      generateRegistryFromInputs = true;
      generateNixPathFromInputs = true;
      linkInputs = true;
    };
  };
}
