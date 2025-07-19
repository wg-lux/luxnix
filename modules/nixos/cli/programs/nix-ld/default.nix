{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.nix-ld;
in {
  options.cli.programs.nix-ld = with types; {
    enable = mkBoolOpt true "Whether or not to enable nix-ld.";
    # libraries: option list of packages
    libraries = mkOption {
      type = types.listOf types.package;
      default = with pkgs; [
          zlib
          fuse3
          icu
          nss
          openssl
          curl
          expat
          libGLU
          libGL
          git
          gitRepo
          gnupg
          autoconf
          procps
          gnumake
          util-linux
          m4
          gperf
          unzip
          xorg.libXi
          xorg.libXmu
          freeglut
          xorg.libXext
          xorg.libX11
          xorg.libXv
          xorg.libXrandr
          ncurses5
          stdenv.cc
          binutils
          pkgs.autoAddDriverRunpath
      ];
      description = "List of libraries to include in nix-ld.";
    };
  };

  config = mkIf cfg.enable {
    programs.nix-ld = {
      enable = true;
      libraries = cfg.libraries;
    };

  };
}
