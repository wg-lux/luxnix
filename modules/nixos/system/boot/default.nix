{
  config,
  lib,
  pkgs,
  ...
}:
let
  inherit (lib) mkIf;
  inherit (lib.luxnix) mkBoolOpt;
  cfg = config.system.boot;
  lanzaboote = config.boot.lanzaboote;
  esp = config.boot.loader.efi.efiSysMountPoint;

  # Only public material reaches hosts. The fleet PKI stays in controller custody
  # (lx_administration/secure_boot.py, docs/secure-boot.md).
  publicDir = ../../../../conf/secure-boot;
  publicFile = name: publicDir + "/${name}";
  provisioned = builtins.pathExists (publicFile "db.pem");
  certificate = "/etc/luxnix/secure-boot/db.pem";
  # Never created: lzbt fails instead of signing when an artifact is missing.
  absentPrivateKey = "/run/luxnix-secure-boot/no-private-key-on-host";

  # lzbt registers controller-signed generations already on the ESP and only
  # needs the private key for missing ones, so a missing signature fails closed.
  keylessInstallHook = pkgs.writeShellScript "luxnix-lanzaboote-install" ''
    set -euo pipefail
    export PATH=${
      lib.makeBinPath [
        pkgs.coreutils
        pkgs.findutils
        pkgs.sbsigntool
      ]
    }
    if [ ! -s ${certificate} ]; then
      echo "ERROR: fleet Secure Boot certificate ${certificate} is not provisioned; see docs/secure-boot.md." >&2
      exit 1
    fi
    if [ -e ${absentPrivateKey} ]; then
      echo "ERROR: a Secure Boot private key must never exist on a host: ${absentPrivateKey}" >&2
      exit 1
    fi
    PATH=${config.systemd.package}/lib/systemd:$PATH
    install_generations() {
      ${lanzaboote.installCommand} \
        ${
          lib.escapeShellArgs [
            "--public-key=${certificate}"
            "--private-key=${absentPrivateKey}"
            esp
          ]
        } /nix/var/nix/profiles/system-*-link
    }
    if ! install_generations; then
      echo "ERROR: the new generation has no controller signature. On the deploy controller run:" >&2
      echo "  devenv shell secure-boot-sign ${config.networking.hostName}" >&2
      exit 1
    fi
    # lzbt does not re-verify installed stubs; every loader and stub must carry the fleet signature.
    find ${esp}/EFI -type f \( -ipath '${esp}/EFI/Linux/*.efi' -o -ipath '${esp}/EFI/systemd/*.efi' \
      -o -ipath '${esp}/EFI/BOOT/*.efi' \) -print0 |
      while IFS= read -r -d "" image; do
        sbverify --cert ${certificate} "$image" >/dev/null 2>&1 || {
          echo "ERROR: $image is not signed by the fleet Secure Boot key." >&2
          exit 1
        }
      done
  '';

  bootArtifacts = pkgs.writeShellApplication {
    name = "luxnix-boot-artifacts";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.e2fsprogs
      pkgs.efitools
      pkgs.python3
      pkgs.sbsigntool
    ];
    text = ''
      die() {
        echo "ERROR: $*" >&2
        exit 1
      }
      usage() {
        echo "Usage: luxnix-boot-artifacts import <archive> | enroll-firmware" >&2
        exit 2
      }
      [ "$(id -u)" -eq 0 ] || die "Run as root (sudo)."
      [ "$#" -ge 1 ] || usage
      case "$1" in
        import)
          [ "$#" -eq 2 ] || usage
          exec python3 -I ${../../../../lx_administration/secure_boot.py} import \
            --esp ${esp} --cert ${certificate} "$2"
          ;;
        enroll-firmware)
          [ "$#" -eq 1 ] || usage
          [ -t 0 ] || die "Firmware enrollment requires a private interactive terminal."
          for variable in PK KEK db; do
            [ -s "/etc/luxnix/secure-boot/$variable.auth" ] || die "$variable.auth is not provisioned."
          done
          # Enrolling keys before the boot chain is signed would leave the host unbootable.
          for image in ${esp}/EFI/BOOT/BOOTX64.EFI ${esp}/EFI/systemd/systemd-bootx64.efi; do
            sbverify --cert ${certificate} "$image" >/dev/null 2>&1 \
              || die "$image is not signed; sign and install a generation first."
          done
          efivars=/sys/firmware/efi/efivars
          setup_mode="$(od -An -t u1 -j4 -N1 "$efivars/SetupMode-8be4df61-93ca-11d2-aa0d-00e098032b8c" | tr -d ' ')"
          [ "$setup_mode" = 1 ] || die "Firmware is not in Secure Boot setup mode."
          for variable in db KEK PK; do
            for file in "$efivars/$variable"-*; do
              [ ! -e "$file" ] || chattr -i "$file"
            done
          done
          # PK last: writing it leaves setup mode.
          efi-updatevar -f /etc/luxnix/secure-boot/db.auth db
          efi-updatevar -f /etc/luxnix/secure-boot/KEK.auth KEK
          efi-updatevar -f /etc/luxnix/secure-boot/PK.auth PK
          echo "Enrolled fleet keys with Microsoft certificates. Reboot and confirm: bootctl status"
          ;;
        *) usage ;;
      esac
    '';
  };
in
{
  options.system.boot = {
    enable = mkBoolOpt false "Whether or not to enable booting.";
    plymouth = mkBoolOpt false "Whether or not to enable plymouth boot splash.";
    secureBoot = mkBoolOpt false "Whether or not to enable lanzaboote secure boot signed by the controller-held fleet key.";
    spaceManagement = mkBoolOpt true "Whether or not to enable boot space management and monitoring.";
  };

  config = mkIf cfg.enable {

    assertions = lib.optionals cfg.secureBoot [
      {
        assertion =
          !lanzaboote.autoGenerateKeys.enable
          && !lanzaboote.autoEnrollKeys.enable
          && !lanzaboote.measuredBoot.enable
          && lanzaboote.extraEfiSysMountPoints == [ ];
        message = "LuxNix Secure Boot supports only controller-held keys and the primary ESP.";
      }
      {
        # The controller rebuilds every boot artifact; host-local initrd secrets cannot be reproduced.
        assertion = config.boot.initrd.secrets == { };
        message = "Controller-signed Secure Boot does not support boot.initrd.secrets.";
      }
    ];

    environment.etc = mkIf (cfg.secureBoot && provisioned) (
      lib.genAttrs
        [
          "luxnix/secure-boot/db.pem"
          "luxnix/secure-boot/PK.auth"
          "luxnix/secure-boot/KEK.auth"
          "luxnix/secure-boot/db.auth"
        ]
        (name: {
          source = publicFile (baseNameOf name);
        })
    );

    environment.systemPackages =
      with pkgs;
      [
        efibootmgr
        efitools
        efivar
        fwupd
      ]
      ++ lib.optionals cfg.secureBoot [
        sbctl
        bootArtifacts
      ];

    boot = {
      kernel.sysctl = {
        "net.core.rmem_max" = config.luxnix.generic-settings.linux.rmemMax;
        "net.core.wmem_max" = config.luxnix.generic-settings.linux.wmemMax;
      };

      kernelParams = lib.optionals cfg.plymouth [
        "quiet"
        "splash"
        "loglevel=3"
        "udev.log_level=0"
      ];
      # initrd.verbose = lib.optionals cfg.plymouth false;
      # consoleLogLevel = lib.optionals cfg.plymouth 0;
      initrd.systemd.enable = true;

      lanzaboote = mkIf cfg.secureBoot {
        enable = true;
        # Public certificate only; lanzaboote requires a bundle path.
        pkiBundle = "/etc/luxnix/secure-boot";
        publicKeyFile = certificate;
        privateKeyFile = absentPrivateKey;
      };

      loader = {
        efi = {
          canTouchEfiVariables = true;
        };

        external.installHook = mkIf cfg.secureBoot (lib.mkForce keylessInstallHook);

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
      #gc = {
      #  automatic = true;
      # dates = "weekly";
      #  options = "--delete-older-than 30d";
      #  persistent = true;
      #};
      settings.auto-optimise-store = true;
    };

    # services.fwupd.enable = true;
  };
}
