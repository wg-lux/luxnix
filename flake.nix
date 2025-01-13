{
  description = "AGL's Nix/NixOS Config";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-24.11";

    home-manager = {
      url = "github:nix-community/home-manager/release-24.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nur = {
      url = "github:nix-community/NUR";
    };

    snowfall-lib = {
      url = "github:snowfallorg/lib";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    deploy-rs = {
      url = "github:serokell/deploy-rs";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nixos-hardware = {
      url = "github:nixos/nixos-hardware";
    };

    sops-nix = {
      url = "github:mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    impermanence.url = "github:nix-community/impermanence";
    # lanzaboote.url = "github:nix-community/lanzaboote";

    nixgl.url = "github:nix-community/nixGL";
    # stylix.url = "github:danth/stylix";
    catppuccin.url = "github:catppuccin/nix";
    nix-index-database.url = "github:nix-community/nix-index-database";

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    nix-ld.url = "github:Mic92/nix-ld/911665df070e3d6c970e5a248fc4a38550bd5689"; #TODO Unpin when naked_asm is stable
    nix-ld.inputs.nixpkgs.follows = "nixpkgs";
    # nix-ld.ref = "v2.0.3";

    nixos-anywhere = {
      url = "github:numtide/nixos-anywhere";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.disko.follows = "disko";
    };

    nixos-generators = {
      url = "github:nix-community/nixos-generators";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    #Basically it just wraps together nix shell -c and nix-index. 
    # You stick a , in front of a command to run it from whatever location it 
    # happens to occupy in nixpkgs without really thinking about it.

    comma = { # https://github.com/nix-community/comma 
      url = "github:nix-community/comma";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # firefox-gnome-theme = {
    #   url = "github:rafaelmardojai/firefox-gnome-theme";
    #   flake = false;
    # };

    catppuccin-obs = {
      url = "github:catppuccin/obs";
      flake = false;
    };

    nix-topology = {
      url = "github:oddlama/nix-topology";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # nixvim = {
    #   url = "github:nix-community/nixvim";
    #   inputs.nixpkgs.follows = "nixpkgs";
    # };

    # gx-nvim = {
    #   url = "github:chrishrb/gx.nvim";
    #   flake = false;
    # };
    # maximize-nvim = {
    #   url = "github:declancm/maximize.nvim";
    #   flake = false;
    # };

    plasma-manager = {
      url = "github:nix-community/plasma-manager";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.home-manager.follows = "home-manager";
    };

    # endoreg-usb-encrypter.url = "github:wg-lux/endoreg-usb-encrypter";
	  # endoreg-usb-encrypter.inputs.nixpkgs.follows = "nixpkgs";


  };

  # https://snowfall.org/guides/lib/quickstart/
  # https://snowfall.org/reference/lib/
  outputs = inputs: let 
    lib = inputs.snowfall-lib.mkLib {
      inherit inputs;
      src = ./.;

      snowfall = { #CHANGEME
        metadata = "luxnix";
        namespace = "luxnix";
        meta = {
          name = "luxnix";
          title = "AG-Lux' Nix Flake";
        };
      };
    };


    
  in
    lib.mkFlake {
      channels-config = {
        allowUnfree = true;
      };

      # Add modules to all homes
      homes.modules = with inputs; [
        plasma-manager.homeManagerModules.plasma-manager
        ../modules/home
      ];

      systems.modules.nixos = with inputs; [
        nix-ld.nixosModules.nix-ld
        # stylix.nixosModules.stylix
        home-manager.nixosModules.home-manager
        disko.nixosModules.disko
        # lanzaboote.nixosModules.lanzaboote
        impermanence.nixosModules.impermanence
        sops-nix.nixosModules.sops
        nix-topology.nixosModules.default
        # authentik-nix.nixosModules.default
      ];

      # systems.hosts.framework.modules = with inputs; [
      #   nixos-hardware.nixosModules.framework-13-7040-amd
      # ];

      # homes.modules = with inputs; [
      #   impermanence.nixosModules.home-manager.impermanence
      # ];

      overlays = with inputs; [
        nixgl.overlay
        nur.overlays.default
        nix-topology.overlays.default
      ];

      deploy = lib.mkDeploy {inherit (inputs) self;};

      checks =
        builtins.mapAttrs
        (system: deploy-lib:
          deploy-lib.deployChecks inputs.self.deploy)
        inputs.deploy-rs.lib;

      topology = with inputs; let
        host = self.nixosConfigurations.${builtins.head (builtins.attrNames self.nixosConfigurations)};
      in
        import nix-topology {
          inherit (host) pkgs; # Only this package set must include nix-topology.overlays.default
          modules = [
            (import ./topology {
              inherit (host) config;
            })
            {inherit (self) nixosConfigurations;}
          ];
        };
    };
}
