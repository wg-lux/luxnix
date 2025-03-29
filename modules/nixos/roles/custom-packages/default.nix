{ lib
, pkgs
, config
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.custom-packages;

  dev01 = [ ];
  dev02 = [ ];
  dev03 = [
    obsidian
    balena-cli
  ];

  kdePlasma = with pkgs; [
    kdePackages.xdg-desktop-portal-kde
    kdePackages.svgpart
    kdePackages.systemsettings
  ];

  baseDevelopment = with pkgs; [
    # vscode-fhs
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
  ];

  cuda = with pkgs; [
    autoAddDriverRunpath
  ];

  ldBase = with pkgs; [
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
    cudaPackages.cutensor
    cudaPackages.libcufft
    cudaPackages.libcurand
    cudaPackages.libcublas
  ];

  customPackages = [
    pkgs.bash
    pkgs.bashInteractive
  ]
  ++ (if cfg.kdePlasma then kdePlasma else [ ])
  ++ (if cfg.baseDevelopment then baseDevelopment else [ ])
  ++ (if cfg.office then office else [ ])
  ++ (if cfg.visuals then visuals else [ ])
  ++ (if cfg.dev01 then dev01 else [ ])
  ++ (if cfg.dev02 then dev02 else [ ])
  ++ (if cfg.dev03 then dev03 else [ ])
  ++ (if cfg.cloud then cloud else [ ])
  ++ (if cfg.protonmail then [
    pkgs.protonmail-bridge-gui
    pkgs.protonmail-desktop
    pkgs.proton-pass
  ] else [ ])
  ++ (if cfg.hardwareAcceleration then [
    pkgs.pciutils
    pkgs.libva

    pkgs.vdpauinfo # sudo vainfo
    pkgs.libva-utils # sudo vainfo
  ] else [ ])
  ;

  ldPackages = lib.mkIf cfg.ld.enable (
    ldBase ++ (if cfg.cuda then ldCuda else [ ])
  );
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
    dev01 = mkBoolOpt false "Add dev01 packages to custom packages";
    dev02 = mkBoolOpt false "Add dev02 packages to custom packages";
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
      libraries = ldPackages;
    };

    programs.obs-studio.enable = cfg.videoEditing;

    programs.thunderbird.enable = cfg.office;

    hardware.graphics = {
      enable = lib.mkDefault cfg.hardwareAcceleration;
      extraPackages = with pkgs; (if cfg.hardwareAcceleration then [
        intel-media-driver
      ] else [ ]);
    };

    environment.variables = { };

  };
}
