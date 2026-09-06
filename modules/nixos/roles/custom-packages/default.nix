{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.custom-packages;

  # Check if both podman and nvidia are enabled
  podmanEnabled =
    (config.services.luxnix.podman.enable or false)
    || (config.services.virtualisation.podman.enable or false)
    || (config.luxnix.generic-settings.virtualization.enable or false);
  nvidiaEnabled =
    (config.luxnix.nvidia-default.enable or false)
    || (config.luxnix.nvidia-prime.enable or false)
    || (config.luxnix.generic-settings.gpu.nvidia.enable or false);

  dev03 = with pkgs; [
    obsidian
    balena-cli
  ];

  kdePlasma = with pkgs; [
    kdePackages.xdg-desktop-portal-kde
    kdePackages.svgpart
    kdePackages.systemsettings
    kdePackages.kwallet
    kdePackages.kwalletmanager
  ];

  baseDevelopment = with pkgs; [
    # vscode-fhs
    nixfmt
    ripgrep
    cacert
    openssl
    vscode
    gparted
    exfatprogs
    ntfs3g
    easyrsa
    e2fsprogs
    keepassxc
    vlc
    bind
    nixd
    fd
    duf
    dust
    dysk
    ncdu
    nix-tree
    nixos-shell
    nix-output-monitor
  ];

  visuals = with pkgs; [
    blender
  ];

  office = with pkgs; [
    libreoffice-qt6-fresh
    hunspell
    hunspellDicts.de_DE
    hunspellDicts.en_US
    pandoc
    obsidian
    spotify
    zotero
  ];

  cloud = with pkgs; [
    nextcloud-talk-desktop
  ];

  ldCuda = with pkgs; [
    # cudaPackages.cudatoolkit
    mesa
    glibc
    glib
    # linuxPackages.nvidia_x11
    xorg.libXi
    xorg.libXmu
    freeglut
    xorg.libXext
    xorg.libX11
    xorg.libXv
    xorg.libXrandr
    ncurses5
    binutils
    autoAddDriverRunpath
    cudaPackages.cuda_nvcc
    cudaPackages.nccl
    cudaPackages.cudnn
    cudaPackages.libnpp
    cudaPackages.libcutensor
    cudaPackages.libcufft
    cudaPackages.libcurand
    cudaPackages.libcublas
  ];

  # Packages for podman + nvidia combination (for development)
  podmanNvidia = with pkgs; [
    cudaPackages.cudatoolkit # Keep for CUDA development
    nvidia-container-toolkit
  ];

  customPackages =
    with pkgs;
    [
      bash
      bashInteractive
      iftop
      bmon
      nload
    ]
    ++ optionals cfg.kdePlasma kdePlasma
    ++ optionals cfg.baseDevelopment baseDevelopment
    ++ optionals cfg.office office
    ++ optionals cfg.visuals visuals
    ++ optionals cfg.dev03 dev03
    ++ optionals cfg.cloud cloud
    ++ optionals cfg.protonmail [
      protonmail-bridge-gui
      protonmail-desktop
      proton-pass
      planify
    ]
    ++ optionals cfg.hardwareAcceleration [
      pciutils
      libva

      vdpauinfo # sudo vainfo
      libva-utils # sudo vainfo
    ]
    ++ optionals (podmanEnabled && nvidiaEnabled) podmanNvidia;

in
{
  options.roles.custom-packages = {
    enable = mkBoolOpt false "Enable common configuration";
    office = mkBoolOpt false "Add Office Packages to custom packages";
    kdePlasma = mkBoolOpt false "Add KDE Plasma Packages to custom packages";
    baseDevelopment = mkBoolOpt false "Add Base Development Packages to custom packages";
    cuda = mkBoolOpt false "Add CUDA packages to custom packages";
    videoEditing = mkBoolOpt false "Add Video Editing packages to custom packages";
    visuals = mkBoolOpt false "Add Visuals packages to custom packages";
    dev03 = mkBoolOpt false "Add dev03 packages to custom packages";
    protonmail = mkBoolOpt false "Add Protonmail packages to custom packages";
    ld = {
      enable = mkBoolOpt true "Enable nix-ld";
    };
    cloud = mkBoolOpt false "Add Cloud packages to custom packages";
    hardwareAcceleration = mkBoolOpt false "Add Hardware Acceleration packages to custom packages";
  };

  config = mkIf cfg.enable {
    environment.systemPackages = customPackages;

    cli.programs.nix-ld = {
      enable = lib.mkForce cfg.ld.enable;
      extraLibraries = optionals cfg.cuda ldCuda;
    };

    programs.obs-studio.enable = cfg.videoEditing;

    programs.thunderbird.enable = false; # cfg.office;

    hardware.graphics = {
      enable = lib.mkDefault cfg.hardwareAcceleration;
      extraPackages = optionals cfg.hardwareAcceleration [
        pkgs.intel-media-driver
      ];
    };

  };
}
