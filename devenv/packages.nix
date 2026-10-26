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
  deadnix
  statix
  flake-checker
  openssh
  openssl
  sops
  tesseract
  # Controller-held fleet Secure Boot keys (lx_administration/secure_boot.py).
  age
  sbctl
  sbsigntool

  # Shared libraries required by Python and media tooling at runtime.
  libglvnd
  glib
  libxcb
  zlib
]
