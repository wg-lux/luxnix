{
  description = "AGL's Nix/NixOS Config";
  nixConfig = {
    extra-substituters = [
      "https://nix-community.cachix.org"
      "https://cuda-maintainers.cachix.org"
    ];
    extra-trusted-public-keys = [
      "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
      "cuda-maintainers.cachix.org-1:0dq3bujKpuEPMCX6U4WylrUDZ9JyUG0VpVZa7CNfq5E="
    ];
  };

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    devenv.url = "github:cachix/devenv";
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
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
    # stylix.url = "github:danth/stylix";
    catppuccin.url = "github:catppuccin/nix";
    nix-index-database.url = "github:nix-community/nix-index-database";

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    # nix-ld.url = "github:Mic92/nix-ld"; #TODO Unpin when naked_asm is stable
    # nix-ld.inputs.nixpkgs.follows = "nixpkgs";
    # # nix-ld.ref = "v2.0.3";

    nixos-anywhere = {
      url = "github:numtide/nixos-anywhere";
      inputs.nixpkgs.follows = "nixpkgs";
      inputs.disko.follows = "disko";
    };

    nixtest = {
      url = "gitlab:TECHNOFAB/nixtest?dir=lib";
    };

    lx-annotate = {
      url = "github:wg-lux/lx-annotate";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    endoreg-db = {
      url = "git+https://github.com/wg-lux/endoreg-db.git?ref=prototype";
      flake = false;
    };

    nixos-generators = {
      url = "github:nix-community/nixos-generators";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    #Basically it just wraps together nix shell -c and nix-index.
    # You stick a , in front of a command to run it from whatever location it
    # happens to occupy in nixpkgs without really thinking about it.

    comma = {
      # https://github.com/nix-community/comma
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

    nixvim = {
      # url = "github:nix-community/nixvim";
      # If you are not running an unstable channel of nixpkgs, select the corresponding branch of nixvim.
      url = "github:nix-community/nixvim/nixos-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };

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
  outputs =
    inputs:
    let
      lib = inputs.snowfall-lib.mkLib {
        inherit inputs;
        src = ./.;

        snowfall = {
          #CHANGEME
          metadata = "luxnix";
          namespace = "luxnix";
          meta = {
            name = "luxnix";
            title = "AG-Lux' Nix Flake";
          };
        };
      };

      base = lib.mkFlake {
        channels-config = {
          allowUnfree = true;
        };

        # Add modules to all homes
        homes.modules = with inputs; [
          plasma-manager.homeModules.plasma-manager
          nixvim.homeModules.nixvim
        ];

        systems.modules.nixos = with inputs; [
          home-manager.nixosModules.home-manager
          disko.nixosModules.disko
          impermanence.nixosModules.impermanence
          sops-nix.nixosModules.sops
          nix-topology.nixosModules.default
          inputs.lx-annotate.nixosModules.default
        ];

        overlays = with inputs; [

          nur.overlays.default
          nix-topology.overlays.default
          (final: _prev: {
            lx-annotate = inputs.lx-annotate.packages.${final.stdenv.hostPlatform.system}.default;
            lx-annotate-feature-specifications = final.runCommand "lx-annotate-feature-specifications" { } ''
              mkdir -p "$out/share/lx-annotate/features"
              cp ${inputs.lx-annotate}/feature-tracking/*.yml \
                "$out/share/lx-annotate/features/"
            '';
          })
        ];

        deploy = lib.mkDeploy { inherit (inputs) self; };

        checks = builtins.mapAttrs (
          _system: deploy-lib: deploy-lib.deployChecks inputs.self.deploy
        ) inputs.deploy-rs.lib;

        topology =
          with inputs;
          let
            host = self.nixosConfigurations.${builtins.head (builtins.attrNames self.nixosConfigurations)};
          in
          import nix-topology {
            inherit (host) pkgs;
            modules = [
              (import ./topology {
                inherit (host) config;
              })
              { inherit (self) nixosConfigurations; }
            ];
          };
      };

      nixtestPackages = builtins.mapAttrs (
        system: _:
        let
          pkgs = import inputs.nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          ntlib = inputs.nixtest.lib { inherit pkgs; };
        in
        {
          nixtests = ntlib.mkNixtest {
            modules = ntlib.autodiscover {
              dir = ./tests/nixtest;
            };
            args = {
              inherit pkgs ntlib;
              repoRoot = ./.;
            };
          };
        }
      ) base.packages;

      nixtestChecks = builtins.mapAttrs (_: packages: { inherit (packages) nixtests; }) nixtestPackages;

    in
    inputs.nixpkgs.lib.recursiveUpdate base {
      packages = nixtestPackages;
      checks = nixtestChecks;
    };
}
