{ pkgs }:
{
  buildInputs = with pkgs; [
    python311Full
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
