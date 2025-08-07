{
  config,
  lib,
  pkgs,
  ...
}: let
  inherit (lib) mkIf;
  inherit (lib.luxnix) mkBoolOpt;
  #CHANGEME Dafuq is this?
  cfg = config.system.boot;
in {
  options.system.boot = {
    enable = mkBoolOpt false "Whether or not to enable booting.";
    plymouth = mkBoolOpt false "Whether or not to enable plymouth boot splash.";
    secureBoot = mkBoolOpt false "Whether or not to enable secure boot.";
    spaceManagement = mkBoolOpt true "Whether or not to enable boot space management and monitoring.";
  };

  config = mkIf cfg.enable {

    boot.kernel.sysctl."net.core.rmem_max" = config.luxnix.generic-settings.linux.rmemMax;
    boot.kernel.sysctl."net.core.wmem_max" = config.luxnix.generic-settings.linux.wmemMax;

    environment.systemPackages = with pkgs;
      [
        efibootmgr
        efitools
        efivar
        fwupd
      ]
      ++ lib.optionals cfg.secureBoot [sbctl];

    boot = {
      # TODO: if plymouth on
      kernelParams = lib.optionals cfg.plymouth [
        "quiet"
        "splash"
        "loglevel=3"
        "udev.log_level=0"
      ];
      # initrd.verbose = lib.optionals cfg.plymouth false;
      # consoleLogLevel = lib.optionals cfg.plymouth 0;
      initrd.systemd.enable = true;

      # lanzaboote = mkIf cfg.secureBoot {
      #   enable = true;
      #   pkiBundle = "/etc/secureboot";
      # };

      loader = {
        efi = {
          canTouchEfiVariables = true;
        };

        systemd-boot = {
          enable = !cfg.secureBoot;
          configurationLimit = if cfg.spaceManagement then 5 else 20;
          editor = false;
        };
      };

      plymouth = {
        enable = cfg.plymouth;
      };
    };

    # Boot space management configuration
    nix = mkIf cfg.spaceManagement {
      gc = {
        automatic = true;
        dates = "weekly";
        options = "--delete-older-than 30d";
        persistent = true;
      };
      settings.auto-optimise-store = true;
    };

    #TODO @Hamzaukw add to documentation
    systemd.services.boot-space-monitor = mkIf cfg.spaceManagement {
      description = "Monitor and clean boot partition space";
      serviceConfig = {
        Type = "oneshot";
        User = "root";
      };
      script = ''
        BOOT_PATH="/boot"
        AVAILABLE=$(df "$BOOT_PATH" | awk 'NR==2 {print $4}')
        AVAILABLE_MB=$((AVAILABLE / 1024))
        
        if [ "$AVAILABLE_MB" -lt 100 ]; then
          echo "Warning: Boot partition space is low ($AVAILABLE_MB MB available)"
          
          # Clean up old boot files if space is critically low
          if [ "$AVAILABLE_MB" -lt 50 ]; then
            echo "Critical: Cleaning up old boot files"
            cd "$BOOT_PATH/EFI/nixos" 2>/dev/null || exit 0
            
            # Keep only 2 newest files of each type
            ls -t kernel-* 2>/dev/null | tail -n +3 | xargs rm -f || true
            ls -t initrd-* 2>/dev/null | tail -n +3 | xargs rm -f || true
            ls -t *.efi 2>/dev/null | tail -n +3 | xargs rm -f || true
            
            echo "Emergency cleanup completed"
            df -h "$BOOT_PATH"
          fi
        else
          echo "Boot partition space OK ($AVAILABLE_MB MB available)"
        fi
      '';
    };

    systemd.timers.boot-space-monitor = mkIf cfg.spaceManagement {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "daily";
        Persistent = true;
      };
    };

    # services.fwupd.enable = true;
  };
}
