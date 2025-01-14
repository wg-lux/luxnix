#!/bin/bash

set -e  # Exit on first error
set -o pipefail  # Pipe errors also cause script to fail

# Define variables
LUKS_PARTITION="/dev/nvme0n1p2"  # LUKS partition
MOUNT_POINT="/mnt"
TARGET_REPO="/home/admin/dev/luxnix"  # Path to the NixOS repo
CRYPT_NAME="cryptroot"
BTRFS_MOUNT_OPTIONS="-o subvol=root"
EFI_PARTITION="/dev/nvme0n1p1"  # EFI partition

# Function to handle errors
handle_error() {
  echo "Error: $1"
  exit 1
}

# Mount and decrypt the filesystem
echo "Unlocking LUKS partition..."
sudo cryptsetup luksOpen "$LUKS_PARTITION" "$CRYPT_NAME" || handle_error "Failed to unlock LUKS partition."

echo "Mounting Btrfs root partition..."
sudo mount $BTRFS_MOUNT_OPTIONS /dev/mapper/$CRYPT_NAME $MOUNT_POINT || handle_error "Failed to mount root partition."

# Mount additional Btrfs subvolumes
echo "Mounting Btrfs subvolumes..."
for subvol in home nix persist var/log; do
  sudo mount -o subvol=$subvol /dev/mapper/$CRYPT_NAME "$MOUNT_POINT/$subvol" || handle_error "Failed to mount subvolume $subvol."
done

# Mount the swap (no mount is needed for the swap file, but ensure it's used)
echo "Setting up swap..."
sudo swapon "$MOUNT_POINT/swap" || handle_error "Failed to activate swap."

# Mount EFI partition
echo "Mounting EFI partition..."
sudo mount "$EFI_PARTITION" "$MOUNT_POINT/boot" || handle_error "Failed to mount EFI partition."

# Enter chroot environment
echo "Entering chroot environment..."
sudo mount --bind /dev $MOUNT_POINT/dev
sudo mount --bind /proc $MOUNT_POINT/proc
sudo mount --bind /sys $MOUNT_POINT/sys
sudo mount --bind /run $MOUNT_POINT/run

# Chroot into the system and perform update
sudo chroot $MOUNT_POINT /bin/bash <<EOF
# Inside chroot

# Go to the target repository
cd $TARGET_REPO || handle_error "Failed to change directory to $TARGET_REPO."

# Fetch updates (git pull)
echo "Fetching updates from the repository..."
git pull || handle_error "Failed to pull latest changes from the repository."

# Run the NixOS rebuild
echo "Running nixos-rebuild..."
sudo nixos-rebuild switch --flake .#gc-06 || handle_error "Failed to rebuild the system."

EOF

# Clean up
echo "Unmounting filesystems..."
sudo umount -R $MOUNT_POINT || handle_error "Failed to unmount filesystems."

echo "Recovery process complete. You can now reboot the system."

