{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.gpu-client-dev;
in {
  options.roles.gpu-client-dev = {
    enable = mkEnableOption "Enable desktop configuration";
  };

  config = mkIf cfg.enable {

    services = {
      ssh.enable = true;
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
          cudatoolkit
          mesa
          glibc
          linuxPackages.nvidia_x11
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

    roles = {
      desktop.enable = true;
    };

    services = {
      luxnix.avahi.enable = false;
      vpn.enable = false; #TODO OPENVPN IMPLEMENTATION
      virtualisation.podman.enable = false;
    };
    
    environment.systemPackages = with pkgs; [
    	vscode
      obsidian
    ];


    
  };
}