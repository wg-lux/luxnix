#!/bin/sh
set -eu

export PATH=/run/wrappers/bin:/run/current-system/sw/bin
USB_ROOT=/run/media/admin/LX-USB-03
LOG_FILE="$USB_ROOT/gc-02-recovery-cleanup.log"

exec >>"$LOG_FILE" 2>&1
echo "=== recovery cleanup started $(date -u --iso-8601=seconds) ==="

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: this recovery script must be authorized through pkexec."
  exit 1
fi

if [ "$(hostname)" != "gc-02" ]; then
  echo "ERROR: refusing to run on host $(hostname); expected gc-02."
  exit 1
fi

if [ ! -d "$USB_ROOT" ]; then
  echo "ERROR: recovery USB is not mounted at $USB_ROOT."
  exit 1
fi

echo "Filesystem usage before cleanup:"
df -hT / /nix /var/log 2>/dev/null || df -hT /

journalctl --rotate
journalctl --vacuum-size=256M
systemd-tmpfiles --clean

# Retain named system generations: never use -d in this automatic path.
nix-collect-garbage

echo "Filesystem usage after cleanup:"
df -hT / /nix /var/log 2>/dev/null || df -hT /
echo "=== recovery cleanup completed $(date -u --iso-8601=seconds) ==="
