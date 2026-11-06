# Signed RAM migration environment

Build a small signed EFI loader and a separate runtime on `/recovery`. At boot,
the loader copies the runtime into RAM, authenticates it and unmounts its source.
Encryption remains an explicit offline operation. Existing boot generations stay.

## 1. Prepare

- Confirm the host, reviewed revision and locked inputs in a clean, committed
  checkout. Use existing [fleet signing custody](secure-boot.md).
- Ask where the backup is and how restoration was tested. A remote backup is
  valid, but the journal, evidence, credentials and reviewed checkout still need
  independent local storage outside the target disks. Preserve the installation
  closure separately; it is not included in the runtime.
- Mount an independent **ext4 or FAT** recovery filesystem at `/recovery`, at its
  filesystem root. Btrfs recovery media and early-boot downloads are unsupported.
- Require systemd-boot, enabled Secure Boot with the fleet certificate enrolled,
  sufficient `/boot` space, and trusted console/BMC access. The target needs
  Python 3.12+, `objcopy`, `sbverify`, `bootctl`, `findmnt`, `lsblk` and `blkid`.

## 2. Build and sign

Run `devenv shell migration-boot build --help`, then supply:

```text
devenv shell migration-boot build <host> \
  --interface <nic> --address <ipv4/prefix> --controller-cidr <ipv4/prefix> \
  --recovery-uuid <filesystem-uuid> --recovery-fstype <ext4|vfat> \
  --output <new-directory> --sign
```

Add `--gateway <ipv4>` if needed. Choose a reachable management network; host VPN
settings and DNS are not inherited. Host identity and administrator keys come
from existing configuration; limits live in `conf/migration-environment.yml`.

For encrypted recovery media, add `--recovery-luks-uuid <outer-luks-uuid>` and
unlock it before staging. Boot requires its password through console/BMC **before
SSH becomes available**. No private key or recovery password is put in the image.

Retain `migration.efi`, `migration.squashfs`, `manifest.json` and the reported EFI
SHA256. The signed loader authenticates the payload; the JSON file is informational.
Unsigned builds cannot pass staging.

## 3. Stage, then arm

Run `devenv shell check-connectivity <host>`, then:

```text
devenv shell stage-migration-boot --limit <host> \
  -e migration_image=<absolute-migration.efi> -e migration_sha256=<digest> \
  -e migration_payload=<absolute-migration.squashfs>
```

This copies artifacts to the target and verifies them without changing boot state.
For another existing recovery mount, add `-e migration_recovery=<mountpoint>`.
After reviewing the result, repeat with **`-e migration_apply=true`** to publish
both artifacts and arm one-shot boot. These commands neither mount storage nor
reboot. The normal boot default must exclude migration entries and stays unchanged.

## 4. Boot and migrate

After the separately authorized reboot, verify the recovery SSH fingerprint on
the trusted console/BMC and pin it before connecting as root on port **2222** with
strict host-key checking. The fingerprint changes each boot; do not trust an
unverified `ssh-keyscan` result.

Use `luxnix-migration --help`, supplying `--host <inventory-host>` and
`--config <independent-checkout>/autoconf/config.yml` for each operation. Follow
[boot storage migration](boot-storage-migration.md) with the saved plan. Preview
before confirmation; target filesystems must be unmounted and swap disabled.
Booting recovery never starts encryption automatically.

Keep recovery material until cold boot, Plymouth unlock, administrator login and
LX-Annotate data access pass. One-shot boot is **not disk rollback**: after root
conversion, the old generation may not boot. Re-select the retained recovery entry
through the boot console to resume an interrupted migration.

## Developer checks

Build a disposable unsigned fixture with `uv run python -m tests.test_migration_loader_vm`.
Set `LUXNIX_MIGRATION_BUNDLE` to its output and `LUXNIX_QEMU` to the QEMU executable;
run `uv run pytest -q tests/test_migration_loader_vm.py`. Requires KVM, mtools,
dosfstools, binutils, OpenSSL and sbsigntool.

VM tests cover RAM startup and tamper rejection. Real firmware trust, networking,
encrypted recovery-media unlock and installation acceptance still need host testing.
