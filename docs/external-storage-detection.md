# External storage detection

**Schema version:** 1

**Service:** `endoreg-mount-persisting-storage.service`

**Timer:** `endoreg-mount-persisting-storage.timer`

**Scope:** Local external-storage discovery and verification; no data migration or device enrollment.

## Detection

**Inventory:** lsblk JSON block-device inventory

**Candidates:** Physical disks marked USB, removable, or hot-pluggable.

**Interval:** 30 seconds after the preceding check completes, with 1 second timer accuracy.

**Timeout:** 30 seconds per check

## States

**Absent:** No enrolled identity and no external disk detected; successful idle check.

**Enrollment required:** External disks detected but no identity enrolled; report candidates without mounting.

**Configured device absent:** The enrolled partition is disconnected and the target is unmounted; successful idle check.

**Verified:** The mounted device matches the enrolled identity before and after the operation.

**Unverified existing mount:** An existing target mount has no enrolled identity; fail and preserve it.

**Lost:** The enrolled device disappeared, changed identity, or differs from the mounted device; fail and preserve the mount.

**Mount failed:** The mount command failed; preserve its exit status and report failure.

## Enrollment

**Source:** Canonical host inventory YAML, followed by Autoconf generation and review.

### Options

- `roles.endoreg-client.paths.storagePersistingDeviceId`
- `roles.endoreg-client.paths.storagePersistingDevicePart`
- `roles.endoreg-client.paths.storagePersistingMountPoint`

**Identity:** Verify the exact /dev/disk/by-id disk basename and intended partition on the host.

**Protection:** Verify encryption and authorized data use before enrollment; discovery does not authorize plaintext storage or raw-media export.

**Prohibited:** Automatic selection, formatting, unlocking, unmounting, or replacement of an unknown disk.

## Diagnostics

- journalctl -u endoreg-mount-persisting-storage.service --since today
- systemctl status endoreg-mount-persisting-storage.timer
- lsblk --json --paths --output NAME,TYPE,TRAN,RM,HOTPLUG

**Logging:** Each decision and mount attempt emits an endoreg.external_storage JSON event.
