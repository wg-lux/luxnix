{
  config,
  pkgs,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.system.nix;
in {
  options.system.nix = with types; {
    enable = mkBoolOpt false "Whether or not to manage nix configuration";
  };

  config = mkIf cfg.enable {
    nixpkgs = {
      config = {
        allowUnfree = true;
        allowUnfreePredicate = _: true;
      };
    };

    #TODO https://github.com/nix-community/nixGL

###########

          # # makes it easy to use "nix run nixGL --impure -- program"
          # default = pkgs.auto.nixGLDefault;

          # nixGLDefault = pkgs.auto.nixGLDefault;
          # nixGLNvidia = pkgs.auto.nixGLNvidia;
          # nixGLNvidiaBumblebee = pkgs.auto.nixGLNvidiaBumblebee;
          # nixGLIntel = pkgs.nixGLIntel;
          # nixVulkanNvidia = pkgs.auto.nixVulkanNvidia;
          # nixVulkanIntel = pkgs.nixVulkanIntel;

###########
    home.packages = with pkgs; [
      nixgl.nixGLIntel
      # nixgl.nvidiaPackages
      # nixgl.
      nix-output-monitor
      nvd
    ];

    systemd.user.startServices = "sd-switch";

    programs = {
      home-manager.enable = true;
    };

    

    nix = {
      settings = {
        trusted-substituters = [
          "https://cache.nixos.org"
          "https://nix-community.cachix.org"
          "https://numtide.cachix.org?priority=42"
        ];

        trusted-public-keys = [
          "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
          "nix-community.cachix.org-1:mB9FSh9qf2dCimDSUo8Zy7bkq5CX+/rkCWyvRCYg3Fs="
          "numtide.cachix.org-1:2ps1kLBUWjxIneOy1Ik6cQjb41X0iXVXeHigGmycPPE="
        ];

        experimental-features = ["nix-command" "flakes"];
        warn-dirty = false;
        use-xdg-base-directories = true;
      };
    };

    news = {
      display = "silent";
      json = lib.mkForce {};
      entries = lib.mkForce [];
    };
  };
}
