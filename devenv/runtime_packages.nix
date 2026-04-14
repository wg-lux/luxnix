{ pkgs, uvPackage, ... }:
let

  runtimePackages = with pkgs; [
    stdenv.cc.cc
    tesseract
    uvPackage
    openssh
    openssl
    sops
    black
    nixfmt
    libglvnd
    glib
    libxcb
    zlib
  ];

in
runtimePackages
