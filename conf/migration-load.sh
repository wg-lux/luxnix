# Sourced by the signed initrd. Every refusal propagates to its fail-closed gate.
# The copy function is also exercised directly with disposable files in tests.
copy_migration_payload() {
    source=$1 destination=$2 expected_hash=$3 expected_size=$4
    test -f "$source" && test ! -L "$source" || return 1
    test ! -e "$destination" && test ! -e "$destination.partial" || return 1
    test "$(stat -c %s "$source")" = "$expected_size" || return 1
    # A growing or substituted source cannot consume unbounded RAM.
    head -c "$((expected_size + 1))" "$source" > "$destination.partial" || return 1
    test "$(stat -c %s "$destination.partial")" = "$expected_size" || return 1
    printf '%s  %s\n' "$expected_hash" "$destination.partial" | sha256sum -c - || return 1
    mv "$destination.partial" "$destination" || return 1
}

load_migration_payload() {
    work=$1 recovery_uuid=$2 recovery_type=$3 payload_hash=$4 payload_size=$5 reserve_mib=$6
    shift 6
    case "$(findmnt -n -o FSTYPE --target "$work")" in
        rootfs|ramfs|tmpfs) ;; *) return 1 ;;
    esac
    test "$(awk 'END {print NR}' /proc/swaps)" = 1 || return 1
    available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    test "$((available * 1024))" -ge "$((payload_size + reserve_mib * 1024 * 1024))" || return 1
    devices=$(blkid -t "UUID=$recovery_uuid" -o device) || return 1
    test "$(printf '%s\n' "$devices" | wc -l)" = 1 || return 1
    test -b "$devices" || return 1
    ancestors=$(lsblk -s -r -n -o TYPE,SERIAL "$devices") || return 1
    disks=$(printf '%s\n' "$ancestors" | awk '$1 == "disk" {print $2}')
    test -n "$disks" || return 1
    test "$(printf '%s\n' "$ancestors" | awk '$1 == "disk" && NF != 2 {print "unknown"}')" = '' || return 1
    for serial in $disks; do
        for target in "$@"; do test "$serial" != "$target" || return 1; done
    done
    case "$recovery_type" in
        ext4) options=ro,noload,nodev,nosuid,noexec ;;
        vfat) options=ro,nodev,nosuid,noexec ;;
        *) return 1 ;;
    esac
    mkdir -p "$work/migration-source" || return 1
    mount -t "$recovery_type" -o "$options" "$devices" "$work/migration-source" || return 1
    # The signed digest is also the immutable payload filename on recovery media.
    if ! copy_migration_payload "$work/migration-source/luxnix-migration/$payload_hash.squashfs" \
        "$work/nix-store.squashfs" "$payload_hash" "$payload_size"; then
        umount "$work/migration-source" || return 1
        return 1
    fi
    umount "$work/migration-source" || return 1
    # NixOS subsequently loop-mounts only this authenticated RAM copy.
    echo 'Migration payload authenticated in RAM; recovery source detached.'
}
