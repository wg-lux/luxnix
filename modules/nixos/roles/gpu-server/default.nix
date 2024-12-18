{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.gpu-server;
in {
  options.roles.gpu-server = {
    enable = mkBoolOpt false ''
      Enable gpu server configuration.
      Enables roles:
      - desktop
      - aglnet.client
    '';
  };

  config = mkIf cfg.enable {

    roles = {
      desktop.enable = true;
      aglnet.client.enable = true;
      base-server.enable = true;
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
          unzip
          cudaPackages.cudatoolkit
          mesa
          glibc
          glib
          linuxPackages.nvidia_x11
          xorg.libXi
          xorg.libXmu
          freeglut
          xorg.libXext
          xorg.libX11
          xorg.libXv
          xorg.libXrandr
          ncurses5
          binutils
          pkgs.autoAddDriverRunpath
          cudaPackages.cuda_nvcc
          cudaPackages.nccl
          cudaPackages.cudnn
          cudaPackages.libnpp
          cudaPackages.cutensor
          cudaPackages.libcufft
          cudaPackages.libcurand
          cudaPackages.libcublas
      ];
    };
    
    boot.binfmt.emulatedSystems = [
      # "aarch64-linux"
    ];

    



    services = {
      luxnix.avahi.enable = false;
      # vpn.enable = false; #TODO OPENVPN IMPLEMENTATION #managed via roles
      virtualisation.podman.enable = false;
    };
    
    environment.systemPackages = with pkgs; [
    	vscode
      obsidian
      e2fsprogs
    ];


    
  };
}
