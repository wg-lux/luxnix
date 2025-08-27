{ pkgs }:
{
  buildInputs = with pkgs; [
    python313Full
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
    cudaPackages.cuda_nvcc
    python313Full
    jq
    age
    openssh
    stdenv.cc.cc
    tesseract
    sops
    openssl
    black
    nixpkgs-fmt
  ];
}
