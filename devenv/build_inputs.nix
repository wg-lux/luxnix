{ pkgs, ... }:
let
  buildInputs = with pkgs; [
    nixpkgs-fmt
    python312
    stdenv.cc.cc
    tesseract
    glib
    openssh
    openssl
    black
    cmake
    gcc
    pkg-config
    protobuf
    libglvnd
  ];

in
buildInputs
