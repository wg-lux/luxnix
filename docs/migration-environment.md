# Signed RAM migration environment

LuxNix builds a small host-bound Unified Kernel Image (UKI) and a separate
SquashFS recovery runtime on demand. Only the UKI goes on the EFI partition;
the runtime is published on an independent filesystem mounted at `/recovery`.
The controller signs the UKI with fleet custody and stages a one-shot
systemd-boot entry. This replaces the boot USB. Root conversion still
runs offline, after the operator has entered the recovery environment and passed
the existing [migration gates](boot-storage-migration.md).

This is an initial implementation, not hardware acceptance evidence. A successful
evaluation or unit test does not prove firmware boot, networking, power-loss
recovery or application data access. Validate those on a disposable machine before
using this workflow for production conversion.

## Ask the operator about recovery

Ask: **Where is your recovery backup: a connected drive or remote backup service?
Have you tested restoring it from the recovery environment?** A connected drive
is expected, but the backup can be remote. Check its network path and credentials
without depending on the root disk that will be encrypted. Never ask users to put
credentials in review notes.

The backup and migration journal serve different purposes. Existing conversion
code requires its journal and recovery evidence on independent durable local
storage; a remote backup does not satisfy that filesystem check. Keep a connected
independent drive for the journal, preserved credentials and reviewed checkout.
No change here weakens the backup, independent custody or restore-test gates.

## Prepare the reviewed image

Use a clean committed durable checkout and the existing
[fleet signing custody](secure-boot.md). Host hardware identity comes from
`autoconf/config.yml`; administrator public keys come from the evaluated host
configuration. Shared limits live in `conf/migration-environment.yml`.

Choose a reachable physical management interface, static IPv4 address, optional
gateway and controller CIDR. The appliance does not inherit host VPN secrets,
applications or disk mounts. Its firewall admits SSH only from that CIDR on the
chosen interface. There is no password login or automatic encryption.

Run `devenv shell migration-boot build --help` for the build interface. Supply the
inventory host, `--interface`, `--address`, `--controller-cidr`, `--recovery-uuid`,
`--recovery-fstype` and a new `--output` directory; add `--gateway` if needed.
Use the recovery filesystem UUID, not its mountpoint or disk label. The initial
implementation supports ext4 and FAT recovery filesystems, mounted at their
filesystem root. It does not support Btrfs recovery volumes or remote fetching
in early boot. This restriction does not change the Btrfs target root support.

If recovery is LUKS-encrypted, also supply `--recovery-luks-uuid` with the outer
LUKS UUID. It must be unlocked already when staging. Boot prompts for its password
through the trusted console/BMC before loading the payload; recovery SSH is not
available until the payload has loaded. No unlock key goes in the UKI. Without
this option staging refuses encrypted recovery media. A non-secret authenticated
payload may instead reside on an unencrypted independent filesystem alongside
separate encrypted credential custody.

Without `--sign` the image is unsigned and
cannot pass staging. Add `--sign` for controller-side signing, using the existing
encrypted custody and protected RAM key workspace. Retain the reported image path
and SHA256. The output directory contains `migration.efi`, `migration.squashfs`
and an informational `manifest.json`. No private key is included in either artifact.

The runtime is built first. Its exact SHA256 and byte length are embedded into
the second, signed loader build. The external JSON manifest is not a trust root.
Early boot resolves the recovery filesystem UUID unambiguously, rejects target
disk serials, mounts recovery read-only without ext4 journal replay, and copies
at most the expected length plus one byte into RAM. It checks the RAM copy before
mounting or executing it, then unmounts the recovery source. Missing media,
tampering, swap, insufficient RAM or a failed unmount stop boot at the console.
The loaded runtime uses only RAM for its root, store and writable overlay.

The image includes Python dependencies, cryptsetup, Btrfs and installation tools.
It does not include the new host's complete installation closure. Preserve that
closure and the exact reviewed migration checkout independently before conversion,
following the existing migration runbook. Ensure the recovery environment can
reach any required package sources; it does not configure DNS for you.

## Stage one host

Confirm the exact host, reviewed revision and locked inputs. Run
`devenv shell check-connectivity <host>` first. The existing target needs Python
3.12 or later, `objcopy`, `sbverify`, `bootctl`, `findmnt`, `lsblk` and `blkid`
on its system PATH. Mount the intended independent recovery filesystem first.
It must use systemd-boot, have the fleet certificate enrolled with Secure Boot
enabled, and have enough free space on the mounted `/boot` ESP. Staging refuses
unknown defaults, insufficient space, different hardware or another armed entry.

Use `devenv shell stage-migration-boot --limit <host>` with
`-e migration_image=<absolute-signed-image>`, `-e migration_sha256=<digest>` and
`-e migration_payload=<absolute-migration.squashfs>`. An alternate existing
recovery mountpoint can be selected with `-e migration_recovery=<mountpoint>`.
This copies public artifacts and helpers to private target staging and verifies
them without changing boot state. It is still a remote-state operation.
After reviewing that result, repeat with `-e migration_apply=true` to publish the
payload as `/recovery/luxnix-migration/<sha256>.squashfs`, publish the small EFI
image and select it for the next boot. Neither command mounts storage or reboots.
Payload verification and durable publication must finish before the one-shot
entry is armed. Existing payloads with different bytes are never overwritten.

The entry is stored outside automatic UKI discovery. The normal boot default must
explicitly match an existing normal generation and exclude migration entries.
Only the next-boot selection changes. Interrupted staging leaves the normal
default intact; signed artifacts remain available for inspection and retry.

## Enter recovery and convert

Arrange trusted console or BMC access before the separately authorized reboot.
The RAM system verifies hardware identity, enabled firmware trust, memory, RAM
root and absence of swap before starting SSH. It generates an ephemeral SSH host
key in RAM and prints its fingerprint on the console. Verify it through that
trusted channel and pin the key in a dedicated known-hosts file before connecting
as root on port 2222 (or the configured policy port), with strict host-key checking.
Do not accept an unverified key from `ssh-keyscan`. The fingerprint changes on
every boot; this initial implementation does not automate remote host attestation.

Use `luxnix-migration --help` in recovery for the existing boot setup interface.
For each operation supply `--host <inventory-host>` and
`--config <independent-checkout>/autoconf/config.yml`; the RAM system has a separate
hostname and does not contain the operational checkout or its saved journal.
Explicitly attach and unlock independent custody, access the saved plan and
reviewed checkout, and follow [boot storage migration](boot-storage-migration.md).
Preview the saved operation before its typed confirmation. The existing checks
still reject mounted target filesystems, target-backed runtime paths and swap.
No conversion starts merely because the machine entered recovery.

After conversion, installation and acceptance must verify the new system's
Plymouth unlock, administrator login and LX-Annotate data access. One-shot boot
is not disk rollback: once encryption changes the root, the previous generation
may no longer boot. The retained recovery entry can be selected again through
the trusted boot console to resume the saved journal. Keep recovery material
until cold-boot and application acceptance pass.

## Developer verification

Build an unsigned disposable fixture with
`uv run python -m tests.test_migration_loader_vm`. This reads the shared test
specification and canonical policy and prints the resulting bundle directory.
Set `LUXNIX_MIGRATION_BUNDLE` to that directory and `LUXNIX_QEMU` to the absolute
`qemu-system-x86_64` executable, then run
`uv run pytest -q tests/test_migration_loader_vm.py`.
The suite needs KVM, mtools, dosfstools, binutils, OpenSSL and sbsigntool.

These tests use only disposable disk-image files, an ephemeral test signing key
and isolated VMs. They test signature tampering, loading the external payload
into RAM, entry into NixOS userspace and rejection of corrupted payloads.
Direct kernel boot in the VM does not prove the real firmware Secure Boot chain,
physical host networking, LUKS recovery-media unlock or installation acceptance.
