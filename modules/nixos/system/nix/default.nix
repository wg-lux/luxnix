{
  config,
  lib,
  ...
}:
#CHANGEME: Add agl admin
with lib;
with lib.luxnix; let
  cfg = config.system.nix;
in {
  options.system.nix = with types; {
    enable = mkBoolOpt false "Whether or not to manage nix configuration";
  };

  config = mkIf cfg.enable {
    nix = {
      settings = {
        trusted-users = ["@wheel" "root" "admin"];
        auto-optimise-store = lib.mkDefault true;
        use-xdg-base-directories = true;
        experimental-features = ["nix-command" "flakes"];
        warn-dirty = false;
        system-features = ["kvm" "big-parallel" "nixos-test"];
      };

      # flake-utils-plus
      generateRegistryFromInputs = true;
      generateNixPathFromInputs = true;
      linkInputs = true;
    };
    # Systemd service and timer for automatic nix store optimization
    /*systemd.services.nix-store-optimise = {
      enable = true;
      description = "Run nix store optimise to deduplicate files";
      serviceConfig = {
        Type = "oneshot"; #uns a command once and then stops immediately
        ExecStart = "/run/current-system/sw/bin/nix store optimise";
      };
    };

    systemd.timers.nix-store-optimise = {
      enable = true;
      description = "Schedule nix store optimisation";
      wantedBy = ["timers.target"];
      timerConfig = {
        OnCalendar = "weekly";  # Runs every week
        Persistent = true; #Ensures optimization runs evenif the system was powered off 
      };
    };*/
  };
}

    
