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
    winapps
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

      vdpauinfo
      libva-utils
    ];

in
{
  # One installation boundary for fleet, role and machine package selections.
  # Derivations from pinned custom flakes use the same interface as nixpkgs.
  options.luxnix.packages = {
    shared = mkOption {
      type = types.listOf types.package;
      default = [ ];
      description = "Fleet-wide packages selected in all/70-packages.yml.";
    };
    roles = mkOption {
      type = types.attrsOf (types.listOf types.package);
      default = { };
      description = "Named package contributions from enabled roles or inventory groups.";
    };
    machine = mkOption {
      type = types.listOf types.package;
      default = [ ];
      description = "Machine-only packages selected in host inventory.";
    };
  };

  options.roles.custom-packages = {
    enable = mkBoolOpt false "Enable common configuration";
    office = mkBoolOpt false "Add Office Packages to custom packages";
    kdePlasma = mkBoolOpt false "Add KDE Plasma Packages to custom packages";
    baseDevelopment = mkBoolOpt false "Add Base Development Packages to custom packages";
    videoEditing = mkBoolOpt false "Add Video Editing packages to custom packages";
    visuals = mkBoolOpt false "Add Visuals packages to custom packages";
    dev03 = mkBoolOpt false "Add dev03 packages to custom packages";
    protonmail = mkBoolOpt false "Add Protonmail packages to custom packages";
    cloud = mkBoolOpt false "Add Cloud packages to custom packages";
    hardwareAcceleration = mkBoolOpt false "Add Hardware Acceleration packages to custom packages";
  };

  config = mkMerge [
    {
      environment.systemPackages = unique (
        config.luxnix.packages.shared
        ++ concatLists (attrValues config.luxnix.packages.roles)
        ++ config.luxnix.packages.machine
      );
    }
    (mkIf cfg.enable {
      luxnix.packages.roles.custom-packages = customPackages;

      programs.obs-studio = {
        enable = mkDefault cfg.videoEditing;
        # The pinned OBS recipe already adds driver runpaths and builds NVENC.
        # Avoid the redundant CUDA hook, which changes the cached derivation.
        package = mkDefault (pkgs.obs-studio.override { cudaSupport = false; });
      };

      hardware.graphics = {
        enable = lib.mkDefault cfg.hardwareAcceleration;
        extraPackages = optionals cfg.hardwareAcceleration [
          pkgs.intel-media-driver
        ];
      };
    })
  ];
}
