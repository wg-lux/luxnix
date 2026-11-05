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
  # The first boot installation runs before /etc is activated.
  verificationCertificate = if provisioned then publicFile "db.pem" else certificate;
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
    if [ ! -s ${verificationCertificate} ]; then
      echo "ERROR: fleet Secure Boot certificate ${verificationCertificate} is not provisioned; see docs/secure-boot.md." >&2
      exit 1
    fi
    if [ -e ${absentPrivateKey} ]; then
      echo "ERROR: a Secure Boot private key must never exist on a host: ${absentPrivateKey}" >&2
      exit 1
    fi
    PATH=${config.systemd.package}/lib/systemd:$PATH
    ${pkgs.python3}/bin/python3 -I ${../../../../lx_administration/secure_boot.py} \
      verify-firmware --cert ${verificationCertificate}
    # Select the pending generation and already signed rollback generations.
    # Legacy unsigned profiles cannot be signed by this keyless host.
    profiles=()
    current_profile="$(basename "$(readlink /nix/var/nix/profiles/system)")"
    for profile in /nix/var/nix/profiles/system-*-link; do
      name="$(basename "$profile")"
      generation="''${name#system-}"
      generation="''${generation%-link}"
      if [ "$name" = "$current_profile" ] || compgen -G "${esp}/EFI/Linux/nixos-generation-$generation-*.efi" >/dev/null; then
        profiles+=("$profile")
      fi
    done
    [ "''${#profiles[@]}" -gt 0 ] || exit 1
    verify_images() {
    # lzbt does not re-verify installed stubs; every loader and stub must carry the fleet signature.
    find ${esp}/EFI -type f \( -ipath '${esp}/EFI/Linux/*.efi' -o -ipath '${esp}/EFI/systemd/*.efi' \
      -o -ipath '${esp}/EFI/BOOT/*.efi' \) -print0 |
      while IFS= read -r -d "" image; do
        sbverify --cert ${verificationCertificate} "$image" >/dev/null 2>&1 || {
          echo "ERROR: $image is not signed by the fleet Secure Boot key." >&2
          exit 1
        }
      done
    }
    # Reject missing or invalid staged signatures before lzbt can write the ESP.
    for profile in "''${profiles[@]}"; do
      name="$(basename "$profile")"
      generation="''${name#system-}"
      generation="''${generation%-link}"
      if ! compgen -G "${esp}/EFI/Linux/nixos-generation-$generation-*.efi" >/dev/null; then
        echo "ERROR: missing controller-signed generation $generation; refusing boot installation." >&2
        exit 1
      fi
    done
    verify_images
    install_generations() {
      ${lanzaboote.installCommand} \
        ${
          lib.escapeShellArgs [
            "--public-key=${verificationCertificate}"
            "--private-key=${absentPrivateKey}"
            esp
          ]
        } "''${profiles[@]}"
    }
    if ! install_generations; then
      echo "ERROR: the new generation has no controller signature. On the deploy controller run:" >&2
      echo "  devenv shell secure-boot-sign ${config.networking.hostName}" >&2
      exit 1
    fi
    verify_images
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
        verify-firmware)
          [ "$#" -eq 1 ] || usage
          exec python3 -I ${../../../../lx_administration/secure_boot.py} verify-firmware --cert ${verificationCertificate}
          ;;
        import)
          [ "$#" -eq 2 ] || usage
          exec python3 -I ${../../../../lx_administration/secure_boot.py} import \
            --esp ${esp} --cert ${verificationCertificate} "$2"
          ;;
        enroll-firmware)
          [ "$#" -eq 1 ] || usage
          [ -t 0 ] || die "Firmware enrollment requires a private interactive terminal."
          for variable in PK KEK db; do
            [ -s "/etc/luxnix/secure-boot/$variable.auth" ] || die "$variable.auth is not provisioned."
          done
          # Enrolling keys before the boot chain is signed would leave the host unbootable.
          for image in ${esp}/EFI/BOOT/BOOTX64.EFI ${esp}/EFI/systemd/systemd-bootx64.efi; do
            sbverify --cert ${verificationCertificate} "$image" >/dev/null 2>&1 \
              || die "$image is not signed; sign and install a generation first."
          done
          # A signed loader alone is insufficient: systemd-boot discovers the
          # installed UKI for the current system profile under EFI/Linux.
          current_profile="$(basename "$(readlink /nix/var/nix/profiles/system)")"
          [[ "$current_profile" =~ ^system-([0-9]+)-link$ ]] || die "Invalid current system profile."
          generation="''${BASH_REMATCH[1]}"
          shopt -s nullglob
          stubs=(${esp}/EFI/Linux/nixos-generation-"$generation"-*.efi)
          shopt -u nullglob
          verified_stub=false
          for stub in "''${stubs[@]}"; do
            if [ -f "$stub" ] && sbverify --cert ${verificationCertificate} "$stub" >/dev/null 2>&1; then
              verified_stub=true
              break
            fi
          done
          "$verified_stub" || die "Current system generation has no signed installed boot stub."
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
    secureBoot = mkBoolOpt false "Whether or not to enable lanzaboote secure boot signed by the controller-held fleet key.";
    spaceManagement = mkBoolOpt true "Whether or not to enable boot space management and monitoring.";
  };

  config = mkIf cfg.enable {

    # Start networking independently of network.target (nixpkgs#368791).
    systemd.services = {
      NetworkManager.wantedBy = lib.mkForce [ "multi-user.target" ];
      NetworkManager-dispatcher.wantedBy = lib.mkForce [ "multi-user.target" ];
      openvpn-aglnet.wantedBy = lib.mkForce [ "multi-user.target" ];
    };

    # Never replace a firmware-enforced boot chain with an unsigned configuration.
    system.preSwitchChecks.secureBootPolicy = lib.mkIf (!cfg.secureBoot) ''
      if [ -d /sys/firmware/efi ]; then
        secure_boot_variable=/sys/firmware/efi/efivars/SecureBoot-8be4df61-93ca-11d2-aa0d-00e098032b8c
        if [ ! -r "$secure_boot_variable" ] ||
           [ "$(${pkgs.coreutils}/bin/stat -c %s "$secure_boot_variable")" != 5 ] ||
           [ "$(${pkgs.coreutils}/bin/od -An -tu1 -j4 -N1 "$secure_boot_variable" | ${pkgs.coreutils}/bin/tr -d ' ')" != 0 ]; then
          echo "ERROR: unsigned boot installation refused: firmware Secure Boot is enabled or unreadable. Review the existing enrolled signing identity." >&2
          exit 1
        fi
      fi
    '';

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

    environment.etc = lib.mkMerge [
      {
        "luxnix/activation-compatibility.json".text = builtins.toJSON {
          version = 1;
          activation =
            lib.mapAttrs
              (_: value: builtins.hashString "sha256" (if builtins.isString value then value else value.text))
              (
                lib.filterAttrs (
                  name: _:
                  !(builtins.elem name [
                    "etc"
                    "binsh"
                    "specialfs"
                    "script"
                  ])
                ) config.system.activationScripts
              );
          units = lib.mapAttrs (_: value: builtins.hashString "sha256" value.text) (
            lib.filterAttrs (
              name: _:
              !(builtins.elem name [
                "sshd.service"
                "firewall.service"
                "nftables.service"
                "systemd-networkd.service"
                "NetworkManager.service"
              ])
            ) config.systemd.units
          );
          etc = lib.mapAttrs (_: value: builtins.hashString "sha256" (builtins.toString value.source)) (
            lib.filterAttrs (
              name: _:
              !(builtins.elem name [
                "luxnix/activation-compatibility.json"
                "nix/registry.json"
                "os-release"
                "lsb-release"
              ])
              && !(lib.any (prefix: lib.hasPrefix prefix name) [
                "ssh/"
                "systemd/"
                "NetworkManager/"
              ])
            ) config.environment.etc
          );
          filesystems = builtins.hashString "sha256" (
            builtins.toJSON (
              lib.mapAttrs (_: value: { inherit (value) device fsType options; }) config.fileSystems
            )
          );
        };
      }
      (mkIf (cfg.secureBoot && provisioned) (
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
      ))
    ];

    environment.systemPackages =
      with pkgs;
      [
        efibootmgr
        efitools
        efivar
        fwupd
        (pkgs.writeShellApplication {
          name = "luxnix-safe-activate";
          runtimeInputs = [
            pkgs.python3
            pkgs.nix
            pkgs.systemd
          ];
          text = ''exec python3 ${../../../../lx_administration/activation.py} "$@"'';
        })
        (pkgs.writeShellApplication {
          name = "luxnix-check-unlock-health";
          runtimeInputs = [
            pkgs.cryptsetup
            pkgs.systemd
          ];
          text =
            let
              storage = config.luxnix.storage.operatorUnlocked;
            in
            if !storage.enable then
              "exit 0"
            else if storage.layout == "boot-luks" then
              config.system.preSwitchChecks.encryptedStorage
            else if storage.unlockMethod == "local-openbao" then
              config.system.preSwitchChecks.openbaoLocalPreflight
            else if storage.unlockMethod == "tpm2" then
              lib.concatMapStringsSep "\n" (
                volume:
                "cryptsetup open --test-passphrase --token-only --token-type systemd-tpm2 --external-tokens-path ${pkgs.systemd}/lib/cryptsetup ${lib.escapeShellArg volume.container}"
              ) (builtins.attrValues storage.volumes)
            else
              "exit 0";
        })
      ]
      ++ lib.optionals cfg.secureBoot [
        sbctl
        bootArtifacts
      ];

    boot = {
      # Keep the unlock prompt on a plain text screen without animation.
      plymouth.theme = lib.mkDefault "details";

      kernel.sysctl = {
        "net.core.rmem_max" = config.luxnix.generic-settings.linux.rmemMax;
        "net.core.wmem_max" = config.luxnix.generic-settings.linux.wmemMax;
      };

      kernelParams = lib.optionals config.boot.plymouth.enable [
        "quiet"
        "splash"
        "loglevel=3"
        "udev.log_level=0"
      ];

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
