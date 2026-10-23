{
  pkgs,
  inputs,
  ...
}:
pkgs.mkShell {
  NIX_CONFIG = "extra-experimental-features = nix-command flakes";

  packages = with pkgs; [
    nh
    inputs.nixos-anywhere.packages.${pkgs.stdenv.hostPlatform.system}.nixos-anywhere
    python312Packages.mkdocs-material
    deploy-rs

    statix
    deadnix
    alejandra
    nixfmt
    flake-checker
    home-manager
    # CI must not depend on a runner-global Python dependency manager.
    uv
    jq
    openssl
    git
    sops
    ssh-to-age
    gnupg
    age
  ];
}
