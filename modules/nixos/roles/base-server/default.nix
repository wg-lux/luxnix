{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.base-server;
in {
  options.roles.base-server = {
    enable = mkEnableOption "Enable base desktop server configuration";
  };

  config = mkIf cfg.enable {

    
    services.ssh = {
      enable = true;
        authorizedKeys = [ 
        "${config.luxnix.generic-settings.rootIdED25519}" 
        ];
      };

    cli.programs.nix-ld = {
      enable = true;
      libraries = with pkgs; [
          stdenv.cc.cc
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
          glib
          glibc
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
    };
    
    boot.binfmt.emulatedSystems = [
      # "aarch64-linux"
    ];

    roles = {
      desktop.enable = true;
    };

    luxnix.boot-decryption-stick = {
      enable = true;
    };

    services = {
      luxnix.avahi.enable = false;
      vpn.enable = false; #TODO OPENVPN IMPLEMENTATION
      virtualisation.podman.enable = false;
    };
    
    environment.systemPackages = with pkgs; [
    	vscode
      obsidian
      spotify
    ];


    
  };
}
