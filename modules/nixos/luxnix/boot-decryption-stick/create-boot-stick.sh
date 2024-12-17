#!/usr/bin/env bash

# Define variables
HOSTNAME=""
USB_DEVICE=""
USB_DEVICE_BY_MOUNT=""
USB_UUID=""
MOUNT_POINT="/mnt/usb_key"
KEYFILE_NAME="keyfile.bin"
# KEYFILE_PATH="$MOUNT_POINT/$KEYFILE_NAME"
 # Placeholder for hostname config path
OFFSET_M=50; # Offset in MiB for the keyfile partition
OFFSET_B=$((OFFSET_M * 1024 * 1024)); # Offset in bytes for the keyfile partition
BS=1;
COUNT=4096;
LUKS_HDD_INTERN_UUID=""
LUKS_SWAP_UUID=""

ADD_KEYFILE="n"

# Pre-requisites
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root"
    exit
fi

# Enter Hostname
read -p "Please enter the hostname: " HOSTNAME 
LUXNIX_PATH="/home/${config.user.admin.name}/luxnix/$HOSTNAME-usb-key.nix"
HOSTNAME_CONFIG_PATH="./$HOSTNAME.nix"

# Step 1: Identify target USB device
# This part requires user interaction. The script will list available USB devices.
echo "Available USB devices:"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT | grep -i "disk"

read -p "Please enter the device path (e.g., /dev/sdb) of the USB drive: " USB_DEVICE
USB_DEVICE_BY_MOUNT="$USB_DEVICE"

# Step 2: Format the USB device (optional)
read -p "Do you want to format the USB stick? (y/n): " FORMAT_USB
if [[ "$FORMAT_USB" == "y" ]]; then
    echo "Formatting $USB_DEVICE_BY_MOUNT..."
    sudo mkfs.ext4 $USB_DEVICE_BY_MOUNT
fi
# get the UUID of the USB device after formatting
USB_UUID=$(blkid -s UUID -o value $USB_DEVICE_BY_MOUNT)
USB_DEVICE="/dev/disk/by-uuid/$USB_UUID"

# Step 3: Mount the USB device
sudo mkdir -p $MOUNT_POINT
sudo mount $USB_DEVICE $MOUNT_POINT

# Step 4: Create key file using dd
echo "Creating keyfile on the USB stick..."
sudo dd if=/dev/urandom of=$KEYFILE_NAME bs=$BS count=$COUNT
sudo chmod 600 $KEYFILE_NAME

# write keyfile to USB stick
sudo dd if=$KEYFILE_NAME of=$USB_DEVICE bs=$BS count=$COUNT seek=$OFFSET_B

# Step 5: Add keyfile using cryptsetup
# Display partition information and let user select luks partition (main filesystem and swap)
echo "Available partitions:"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,UUID

read -p "Please enter the UUID of the LUKS partition for the main filesystem (e.g., luks-UUID; only enter UUID): " LUKS_HDD_INTERN_UUID
read -p "Please enter the UUID of the LUKS partition for the swap (e.g., luks-UUID; only enter UUID): " LUKS_SWAP_UUID

# Print device info for confirmation
echo "LUKS HDD Intern UUID: $LUKS_HDD_INTERN_UUID"
echo "LUKS Swap UUID: $LUKS_SWAP_UUID"

# Confirm with user
read -p "Do you want to proceed with adding the keyfile to the LUKS partitions? (y/n): " ADD_KEYFILE

if [[ "$ADD_KEYFILE" == "y" ]]; then
    echo "Adding keyfile to LUKS partitions..."
    # Ensure cryptsetup is properly referenced
    sudo cryptsetup luksAddKey /dev/disk/by-uuid/$LUKS_HDD_INTERN_UUID $KEYFILE_NAME
    sudo cryptsetup luksAddKey /dev/disk/by-uuid/$LUKS_SWAP_UUID $KEYFILE_NAME
fi

# Step 7: Create .nix configuration file with the correct structure
echo "Generating NixOS configuration file..."

cat <<EOF > $LUXNIX_PATH
let 
  # Import hardware configuration based on the provided hostname config file

  ## Also possible to import from a separate file
  # hardware = import $HOSTNAME_CONFIG_PATH;
  # filesystem-luks-uuid = hardware.luks-hdd-intern-uuid;
  # swap-luks-uuid = hardware.luks-swap-uuid;

  filesystem-luks-uuid = "$LUKS_HDD_INTERN_UUID";
  swap-luks-uuid = "$LUKS_SWAP_UUID";
  usb-uuid = "$USB_UUID";
  usb-mountpoint = "$MOUNT_POINT";
  usb-device = "$USB_DEVICE";

  bs = $BS;
  offset-m = $OFFSET_M;
  offset-b = $OFFSET_B;
  keyfile-size = $COUNT;

in {

    boot.initrd.availableKernelModules = [ "dm-crypt" "sd_mod" "usb_storage"];

    boot.initrd.luks.devices."luks-$LUKS_HDD_INTERN_UUID" = {
        keyFile       = usb-device;
        keyFileOffset = offset-b;
        keyFileSize   = keyfile-size;
        preLVM        = true;
        fallbackToPassword = true;
    };

    boot.initrd.luks.devices."luks-$LUKS_SWAP_UUID" = {
        keyFile       = usb-device;
        keyFileOffset = offset-b;
        keyFileSize   = keyfile-size;
        preLVM        = true;
        fallbackToPassword = true;
    };
}
EOF

echo "NixOS configuration file created at $LUXNIX_PATH"

# Step 7: Unmount the USB stick
sudo umount $MOUNT_POINT
sudo rmdir $MOUNT_POINT

# changing permission of the keyfile

echo "Script completed successfully!"
