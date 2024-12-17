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

    roles = {
      desktop.enable = true;
      aglnet.client.enable = true;
      endoreg-client.enable = true;
    };

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
