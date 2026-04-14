{ pkgs }:
{
  buildInputs = with pkgs; [
    # python313Full
    stdenv.cc.cc
    tesseract
    glib
    openssh
    openssl
    black
    nixpkgs-fmt
    ansible-lint
  ];

  packages = with pkgs; [
    # cudaPackages.cuda_nvcc  # moved to host configs - too heavy for dev shell
    jq
    age
    openssh
    git
    stdenv.cc.cc
    tesseract
    sops
    openssl
    black
    nixpkgs-fmt
    pre-commit
  ];
}
