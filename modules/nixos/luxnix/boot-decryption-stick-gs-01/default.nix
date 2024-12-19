{ lib, config, pkgs, ... }:
with lib;
with lib.luxnix;

let
  cfg = config.luxnix.boot-decryption-stick-gs-01;
  hostname = config.networking.hostName;

  # Offset in bytes for the keyfile partition
  offsetB = cfg.offsetM * 1024 * 1024;


  #"${cfg.scriptName}" ''
  scriptPath = pkgs.writeShellScriptBin "gs-01-bootstick" '' 
    #!/usr/bin/env bash
    set -euo pipefail

    HOSTNAME=${hostname}
    NIX_CONFIGURATION_OUTPUT="${cfg.configurationOutputPath}"
    MOUNT_POINT="${cfg.mountPoint}"
    KEYFILE_NAME="${cfg.keyfileName}"
    OFFSET_M=${toString cfg.offsetM}
    OFFSET_B=${toString offsetB} # Offset in bytes for the keyfile partition
    BS=${toString cfg.bs}         # Block size for the keyfile
    COUNT=${toString cfg.count}   # Number of blocks for the keyfile

    USB_DEVICE=""
    USB_DEVICE_BY_MOUNT=""
    USB_UUID=""

    ADD_KEYFILE="n"

    # Pre-requisites
    if [ "$EUID" -ne 0 ]; then
        echo "Please run as root"
        exit 1
    fi

    # Step 1: Identify target USB device
    # List available USB devices.
    echo "Available USB devices:"
    lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -i "disk"

    read -p "Please enter the device path (e.g., /dev/sdb) of the USB drive: " USB_DEVICE
    USB_DEVICE_BY_MOUNT="$USB_DEVICE"

    # Step 2: Optional formatting of the USB device
    read -p "Do you want to format the USB stick? (y/n): " FORMAT_USB
    if [[ "$FORMAT_USB" == "y" ]]; then
        echo "Formatting $USB_DEVICE_BY_MOUNT..."
        mkfs.ext4 "$USB_DEVICE_BY_MOUNT"
    fi

    # Retrieve the UUID of the USB device
    USB_UUID=$(blkid -s UUID -o value "$USB_DEVICE_BY_MOUNT")
    USB_DEVICE="/dev/disk/by-uuid/$USB_UUID"

    # Step 3: Mount the USB device
    mkdir -p "$MOUNT_POINT"
    mount "$USB_DEVICE" "$MOUNT_POINT"

    # Step 4: Create key file on the USB stick
    echo "Creating keyfile on the USB stick..."
    dd if=/dev/urandom of="$KEYFILE_NAME" bs="$BS" count="$COUNT"
    chmod 600 "$KEYFILE_NAME"

    # Write the keyfile data into the USB device at OFFSET_B
    dd if="$KEYFILE_NAME" of="$USB_DEVICE" bs="$BS" count="$COUNT" seek=$(($OFFSET_B/$BS))

    # Confirm adding the keyfile to cryptroot
    read -p "Do you want to proceed with adding the keyfile to cryptroot? (y/n): " ADD_KEYFILE

    if [[ "$ADD_KEYFILE" == "y" ]]; then
        echo "Adding keyfile to cryptroot0..."

        # For the primary disk setup, the luks partition is labeled as "luks0"
        # Disko defines "cryptroot0" as the name of the LUKS container.
        # This is accessible at:
        # /dev/disk/by-partlabel/luks0
        LUKS_DEVICE="/dev/disk/by-partlabel/luks0"
        cryptsetup luksAddKey "$LUKS_DEVICE" "$KEYFILE_NAME"

        echo "Adding keyfile to cryptroot1..."
        # /dev/disk/by-partlabel/luks1
        LUKS_DEVICE="/dev/disk/by-partlabel/luks1"
        cryptsetup luksAddKey "$LUKS_DEVICE" "$KEYFILE_NAME"
        
        echo "Adding keyfile to cryptroot2..."
        # /dev/disk/by-partlabel/luks2
        LUKS_DEVICE="/dev/disk/by-partlabel/luks3"
        cryptsetup luksAddKey "$LUKS_DEVICE" "$KEYFILE_NAME"
    fi

    # Step 6: Create .nix configuration file with the correct structure
    echo "Generating NixOS configuration file..."

    cat <<EOF > $NIX_CONFIGURATION_OUTPUT
    let
      usb-uuid = "$USB_UUID";
      usb-mountpoint = "$MOUNT_POINT";
      usb-device = "$USB_DEVICE";

      bs = $BS;
      offset-m = $OFFSET_M;
      offset-b = $OFFSET_B;
      keyfile-size = $COUNT;
    in {
      # Ensure necessary kernel modules for USB and LUKS
      boot.initrd.availableKernelModules = [ "dm-crypt" "sd_mod" "usb_storage" ];

      # Use the usb-device as keyFile, with offset and size defined above.
      # Adjust the LUKS device naming to match the updated configuration.
      boot.initrd.luks.devices."cryptroot0" = {
        keyFile        = usb-device;
        keyFileOffset  = offset-b;
        keyFileSize    = keyfile-size;
        preLVM         = true;
        keyFileTimeout = 10;
      };
      boot.initrd.luks.devices."cryptroot1" = {
        keyFile        = usb-device;
        keyFileOffset  = offset-b;
        keyFileSize    = keyfile-size;
        preLVM         = true;
        keyFileTimeout = 10;
      };
      boot.initrd.luks.devices."cryptroot2" = {
        keyFile        = usb-device;
        keyFileOffset  = offset-b;
        keyFileSize    = keyfile-size;
        preLVM         = true;
        keyFileTimeout = 10;
      };
    }
    EOF

    # set owner to ${config.user.admin.name}
    chown ${config.user.admin.name}:users $NIX_CONFIGURATION_OUTPUT

    echo "NixOS configuration file created at $NIX_CONFIGURATION_OUTPUT"

    # Step 7: Unmount the USB stick
    umount "$MOUNT_POINT"
    rmdir "$MOUNT_POINT"

    # print generated file content to console
    echo "Generated NixOS configuration file content:"
    cat $NIX_CONFIGURATION_OUTPUT

    echo "Script completed successfully!"
  '';

in {
  options.luxnix.boot-decryption-stick-gs-01 = {
    enable = mkBoolOpt false "Enable boot stick with keyfile configuration";

    offsetM = mkOption {
      type = types.int;
      default = 50;
      description = "Offset in MiB for the keyfile.";
    };

    bs = mkOption {
      type = types.int;
      default = 1;
      description = "Block size for the keyfile.";
    };

    count = mkOption {
      type = types.int;
      default = 4096;
      description = "Number of blocks for the keyfile.";
    };

    scriptName = mkOption {
      type = types.str;
      default = "boot-decryption-stick-setup-02";
      description = "Name of the script that will be created.";
    };

    configurationOutputPath = mkOption {
      type = types.path;
      default = "${config.luxnix.generic-settings.systemConfigurationPath}/boot-decryption-config.nix";
      description = "Path to the NixOS configuration file.";
    };

    mountPoint = mkOption {
      type = types.str;
      default = "/mnt/usb_key";
      description = "Mount point for the USB key.";
    };

    keyfileName = mkOption {
      type = types.str;
      default = "keyfile.bin";
      description = "Name of the keyfile.";
    };

  };

  # When enabled, the script and its requirements are made available
  config = mkIf cfg.enable {
    environment.systemPackages = with pkgs; [
      scriptPath
      parted
      cryptsetup
    ];
  };
}
