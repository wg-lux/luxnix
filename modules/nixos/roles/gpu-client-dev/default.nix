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

    services.ssh = {
      enable = true;
        authorizedKeys = [ # just adds authorized keys for admin user, does not enable ssh!
        "${config.luxnix.generic-settings.rootIdED25519}" 
        ];
      };

    
    cli.programs.nix-ld = {
      enable = lib.mkForce true;
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


    luxnix.gpu-eval.enable = lib.mkDefault false;

    roles = {
      desktop.enable = true;
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
      spotify
      keepassxc
      blender
    ];


    
  };
}
