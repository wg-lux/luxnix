{
  config,
  lib,
  ...
}:
let
  inherit (lib) mkDefault mkIf;
  inherit (lib.luxnix) mkBoolOpt;

  cfg = config.system.nix;
  endoregServiceUserName = config.user.endoreg-service-user.name;
  trustedUsers = [
    "@wheel"
    "root"
    "admin"
    endoregServiceUserName
  ];
in
{
  options.system.nix = {
    enable = mkBoolOpt false "Whether or not to manage nix configuration";
  };

  config = mkIf cfg.enable {
    nix = {
      settings = {
        trusted-users = trustedUsers;
        auto-optimise-store = mkDefault true;
        use-xdg-base-directories = true;
        experimental-features = [
          "nix-command"
          "flakes"
        ];
        warn-dirty = false;
        system-features = [
          "kvm"
          "big-parallel"
          "nixos-test"
        ];
      };

      # flake-utils-plus
      generateRegistryFromInputs = true;
      generateNixPathFromInputs = true;
      linkInputs = true;
    };
  };
}
