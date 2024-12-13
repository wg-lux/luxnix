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
    enable = mkBoolOpt false ''
      Enable desktop configuration for gpu development clients.
      Enables roles:
      - desktop
      - aglnet.client
    '';
  };

  config = mkIf cfg.enable {

    services = {
      ssh.enable = true;
      ssh.authorizedKeys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M" #lux@gc-06
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
          unzip
          cudaPackages_11.cudatoolkit
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
          cudaPackages_11.cuda_nvcc
          cudaPackages_11.nccl
          cudaPackages_11.cudnn
          cudaPackages_11.libnpp
          cudaPackages_11.cutensor
          cudaPackages_11.libcufft
          cudaPackages_11.libcurand
          cudaPackages_11.libcublas
      ];
    };
    
    boot.binfmt.emulatedSystems = [
      # "aarch64-linux"
    ];

    roles = {
      desktop.enable = true;
      aglnet.client.enable = true; 
    };

    services = {
      luxnix.avahi.enable = false;
      # vpn.enable = false; #TODO OPENVPN IMPLEMENTATION #managed via roles
      virtualisation.podman.enable = false;
    };
    
    environment.systemPackages = with pkgs; [
    	vscode
      obsidian
    ];


    
  };
}
