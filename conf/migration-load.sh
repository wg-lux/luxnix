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

# Every refusal names its reason on the screen; none of these values is secret.
refuse_migration_payload() {
    echo "Migration payload refused: $*" >&2
    return 1
}

# USB drives can appear seconds after the device queue first settles.
RECOVERY_WAIT_SECONDS=${RECOVERY_WAIT_SECONDS:-60}

load_migration_payload() {
    work=$1 recovery_uuid=$2 recovery_type=$3 payload_hash=$4 payload_size=$5 reserve_mib=$6
    shift 6
    case "$(findmnt -n -o FSTYPE --target "$work")" in
        rootfs|ramfs|tmpfs) ;;
        *) refuse_migration_payload "the early boot root is not in RAM"; return 1 ;;
    esac
    test "$(awk 'END {print NR}' /proc/swaps)" = 1 ||
        { refuse_migration_payload "swap is active"; return 1; }
    available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
    test "$((available * 1024))" -ge "$((payload_size + reserve_mib * 1024 * 1024))" ||
        { refuse_migration_payload "not enough free memory for the runtime"; return 1; }
    waited=0
    until devices=$(blkid -t "UUID=$recovery_uuid" -o device) && test -n "$devices"; do
        if test "$waited" -ge "$RECOVERY_WAIT_SECONDS"; then
            refuse_migration_payload "no recovery drive with filesystem $recovery_uuid" \
                "appeared within $RECOVERY_WAIT_SECONDS seconds; connect it and restart"
            return 1
        fi
        test "$waited" != 0 || echo "Waiting for the recovery drive $recovery_uuid ..." >&2
        sleep 1
        waited=$((waited + 1))
    done
    test "$(printf '%s\n' "$devices" | wc -l)" = 1 ||
        { refuse_migration_payload "several filesystems carry the recovery UUID"; return 1; }
    test -b "$devices" ||
        { refuse_migration_payload "$devices is not a block device"; return 1; }
    ancestors=$(lsblk -s -r -n -o TYPE,SERIAL "$devices") ||
        { refuse_migration_payload "cannot read the disks behind $devices"; return 1; }
    disks=$(printf '%s\n' "$ancestors" | awk '$1 == "disk" {print $2}')
    test -n "$disks" ||
        { refuse_migration_payload "the recovery drive reports no serial number"; return 1; }
    test "$(printf '%s\n' "$ancestors" | awk '$1 == "disk" && NF != 2 {print "unknown"}')" = '' ||
        { refuse_migration_payload "a disk behind the recovery drive has no serial number"; return 1; }
    for serial in $disks; do
        for target in "$@"; do
            test "$serial" != "$target" ||
                { refuse_migration_payload "the recovery filesystem is on a target disk"; return 1; }
        done
    done
    case "$recovery_type" in
        # Read-only without journal or log replay: the drive is never written here.
        ext4) options=ro,noload,nodev,nosuid,noexec ;;
        btrfs) options=ro,nologreplay,nodev,nosuid,noexec ;;
        *) refuse_migration_payload "unsupported recovery filesystem $recovery_type"; return 1 ;;
    esac
    mkdir -p "$work/migration-source" || return 1
    mount -t "$recovery_type" -o "$options" "$devices" "$work/migration-source" ||
        { refuse_migration_payload "cannot mount $devices read-only"; return 1; }
    # The signed digest is also the immutable payload filename on recovery media.
    if ! copy_migration_payload "$work/migration-source/luxnix-migration/$payload_hash.squashfs" \
        "$work/nix-store.squashfs" "$payload_hash" "$payload_size"; then
        umount "$work/migration-source" || return 1
        refuse_migration_payload "luxnix-migration/$payload_hash.squashfs is missing on" \
            "the recovery drive or does not match this boot entry; stage it again"
        return 1
    fi
    umount "$work/migration-source" || return 1
    # NixOS subsequently loop-mounts only this authenticated RAM copy.
    echo 'Migration payload authenticated in RAM; recovery source detached.'
}
