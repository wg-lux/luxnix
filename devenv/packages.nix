{ pkgs, uvPackage, ... }:
with pkgs;
[
  # Build tools required by Python packages with native extensions.
  stdenv.cc.cc
  cmake
  pkg-config
  protobuf

  # Commands used by repository workflows and Devenv tasks.
  uvPackage
  jq
  git
  secretspec
  nixd
  nixfmt
  openssh
  openssl
  sops
  tesseract

  # Shared libraries required by Python and media tooling at runtime.
  libglvnd
  glib
  libxcb
  zlib
]
