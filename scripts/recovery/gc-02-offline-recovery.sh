#!/bin/sh
set -eu

export PATH=/run/wrappers/bin:/run/current-system/sw/bin
TARGET=/dev/disk/by-partlabel/luks
MAPPING=gc02-recovery-root
MOUNT_ROOT=/mnt/gc-02

echo "gc-02 offline storage recovery"
echo "This tool only accepts a non-USB NVMe partition labeled 'luks'."
lsblk -o NAME,PATH,TYPE,TRAN,RM,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL

if [ ! -b "$TARGET" ]; then
  echo "ERROR: no block device exists at $TARGET."
  exit 1
fi

target_real=$(readlink -f "$TARGET")
parent_name=$(lsblk -ndo PKNAME "$target_real")
parent_device="/dev/$parent_name"
transport=$(lsblk -dno TRAN "$parent_device" | tr -d ' ')
removable=$(lsblk -dno RM "$parent_device" | tr -d ' ')

if [ "$transport" != "nvme" ] || [ "$removable" != "0" ]; then
  echo "ERROR: refusing target $target_real on $parent_device (transport=$transport, removable=$removable)."
  exit 1
fi

printf "Type CLEAN-gc-02 to unlock and clean %s: " "$target_real"
read -r approval
if [ "$approval" != "CLEAN-gc-02" ]; then
  echo "Cancelled."
  exit 1
fi

cryptsetup open "$target_real" "$MAPPING"
trap 'umount -R "$MOUNT_ROOT" 2>/dev/null || true; cryptsetup close "$MAPPING" 2>/dev/null || true' EXIT

mkdir -p "$MOUNT_ROOT"
mount -o subvol=root,compress=zstd,noatime "/dev/mapper/$MAPPING" "$MOUNT_ROOT"
mkdir -p "$MOUNT_ROOT/nix" "$MOUNT_ROOT/var/log"
mount -o subvol=nix,compress=zstd,noatime "/dev/mapper/$MAPPING" "$MOUNT_ROOT/nix"
mount -o subvol=log,compress=zstd,noatime "/dev/mapper/$MAPPING" "$MOUNT_ROOT/var/log"

echo "Usage before cleanup:"
df -hT "$MOUNT_ROOT" "$MOUNT_ROOT/nix" "$MOUNT_ROOT/var/log"

# Offline journal vacuum is bounded and preserves recent diagnostic records.
journalctl --directory="$MOUNT_ROOT/var/log/journal" --vacuum-size=256M || true

# Remove only old entries from temporary directories on the installed root.
find "$MOUNT_ROOT/tmp" -xdev -mindepth 1 -mtime +1 -delete 2>/dev/null || true
find "$MOUNT_ROOT/var/tmp" -xdev -mindepth 1 -mtime +7 -delete 2>/dev/null || true

sync
echo "Usage after bounded cleanup:"
df -hT "$MOUNT_ROOT" "$MOUNT_ROOT/nix" "$MOUNT_ROOT/var/log"
echo "Cleanup complete. Reboot the installed system, then run nix-collect-garbage there if more space is needed."
