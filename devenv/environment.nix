{ pkgs, ... }:

let
  buildInputs = with pkgs; [
    python311Full
    stdenv.cc.cc
    tesseract
    glib
    openssh
    openssl
    black
    nixpkgs-fmt
  ];
in
{
  # Add environment variables, packages, shell hooks, etc.
  packages = with pkgs; [
    cudaPackages.cuda_nvcc
    age
    openssh
    stdenv.cc.cc
    tesseract
    sops
    openssl
    black
    nixpkgs-fmt  # NOTE: Will be deprecated -> 'nixfmt'
  ];

  env = {
    # Example: Setting LD_LIBRARY_PATH to contain certain libraries
    LD_LIBRARY_PATH = "${lib.makeLibraryPath buildInputs}:/run/opengl-driver/lib:/run/opengl-driver-32/lib";
  };

  # Configure languages (in your case, Python with uv)
  languages.python = {
    enable = true;
    uv = {
      enable = true;
      sync.enable = true;
    };
  };

  # Shell hooks (e.g., commands to run when entering the shell)
  enterShell = ''
    . .devenv/state/venv/bin/activate
    hello
  '';

  enterTest = ''
    nvcc -V
    python -m unittest
  '';
}
