{
  pkgs,
  uvPackage,
  ...
}:
let
  packages = import ./packages.nix { inherit pkgs uvPackage; };
  managementSystem = import ./management.nix { inherit pkgs; };
in
{
  inherit packages;
  inherit (managementSystem) scripts processes tasks;
}
