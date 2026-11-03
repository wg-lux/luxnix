# Hardware Setup

This document covers hardware prerequisites and host-specific files required before deployment.

## Prerequisites

- An `x86_64-linux` target supported by the selected host configuration
- A firmware mode supported by that configuration (UEFI or BIOS)
- At least one storage device (NVMe or SATA)
- Optional USB stick for boot decryption
- Optional FIDO2 key

Check UEFI mode:

```bash
[ -d /sys/firmware/efi ] && echo "UEFI" || echo "BIOS"
```

## Choose the host files

`systems/x86_64-linux/<host>/default.nix` is the only file required for every
exported host. It is a generated output; change inventory inputs or templates
and regenerate it instead of editing it directly.

The optional Home Manager output is also generated:

- `homes/x86_64-linux/<user>@<host>/default.nix`: Required only when the host
  has a Home Manager configuration. Configure it through
  `ansible/inventory/home-hosts.yml` and
  `ansible/inventory/host_vars/home/<host>.yml`.

Only the adjacent hardware files below are maintained beside the generated
system entry point:

| File | When it is needed |
| --- | --- |
| `disks.nix` | Required when the host entry point imports it for a disko-based installation. |
| `hardware-configuration.nix` | Required only when the host entry point imports generated hardware configuration. |

Inspect the imports in the generated `default.nix` before creating either
adjacent file. An unused hardware file makes ownership less clear and does not
affect evaluation.

## Hardware-configuration workflow

Use this workflow only when the selected host imports
`hardware-configuration.nix`:

1. Boot installer on target machine.
2. Run:

```bash
sudo nixos-generate-config
cat /etc/nixos/hardware-configuration.nix
```

3. Copy relevant hardware fields into:
   - `systems/x86_64-linux/<host>/hardware-configuration.nix`

Do not add that file solely because `nixos-generate-config` produced one; the
host entry point must import it for the file to be effective.

## Disk setup validation

When `default.nix` imports `disks.nix`, inspect the target machine before
deployment:

```bash
lsblk
```

Then verify:

- Device paths in `disks.nix` are correct
- Partitioning/encryption layout matches your intent

## Mount configured persistent storage

For a machine whose persistent-storage provider, expected drive serial, and
mount point are already configured, the cataloged local helper is:

```bash
devenv shell mount-persisting-storage
```

Inspect `lsblk` first and confirm the selected device. The helper reads
sensitive storage settings and may mount a local device, so treat it as a
confirmation-required operation; do not pass credentials on the command line.

## First rebuild commands

Use canonical commands first:

```bash
sudo nixos-rebuild switch --flake .
nh home switch
```

Alias equivalents:

- `nho` -> `sudo nixos-rebuild switch --flake .`
- `nhh` -> `nh home switch`

## Password/secret path note

If your setup uses managed admin passwords, follow [Admin Password Creation and Rotation](./admin-passwords.md).
Do not rely on undocumented local paths like `etc/user-password/files`.

## Boot decryption setup

LuxNix provides the opt-in `boot-decryption-stick` enrollment command and
compatibility command names for gs-01 and gs-02. They share one implementation.
The old ext4/raw-offset layout is unsafe and is no longer accepted. Do not rerun
an old setup command, format an existing stick, or remove an enrolled keyslot to
migrate it. Retain the old stick and independently tested recovery credentials
until a separately prepared replacement has passed a real cold-boot test.

Prepare a **separate, dedicated GPT Linux-reserved partition** through a reviewed
operator partitioning procedure. Its type GUID must be
`8DA63339-0007-60C0-C436-083AC8230908`, its partition label `luxnix-boot-key`,
and its selected key region all zero. It must have no filesystem/signatures,
mounts or device holders. Enrollment never partitions, formats or mounts a disk.
Never repurpose a filesystem partition by changing only its type or label.
The stick contains an unencrypted unlock credential: physically protect it and
keep independent recovery custody. A dedicated partition reserves the key bytes
from filesystem allocation; it does not conceal those bytes.

After enabling the appropriate module and rebuilding through the reviewed
workflow, run its command as root with
`--key-partition /dev/disk/by-partuuid/<reviewed-PARTUUID>`. Review the LUKS
partition labels configured by that module and choose a new
`configurationOutputPath`; existing output is preserved. Confirm the displayed
PARTUUID explicitly. All swap must be disabled during enrollment. The key lives
only in an anonymous RAM descriptor, is written and read back on the reserved
partition, enrolled into each LUKS target and tested before configuration
publication. It is never written to the invoking directory. The key length is
exactly `bs * count` bytes; offsets are exact bytes within the reserved partition
and never rounded by block size. `offsetM` now defaults to zero. An interrupted
enrollment retains both the partition and existing keyslots for operator review;
do not retry by replacing the key bytes. The pure renderer can reconstruct the
configuration from the recorded PARTUUID, byte offset and total key size.

For review-only rendering, use `luxnix-render-boot-decryption-config` with
`--key-partuuid`, `--offset-bytes`, `--keyfile-size` and `--luks-device`.
The removed `--usb-uuid` filesystem-offset contract fails closed. See
[Nix Quality](./nix-quality.md#generated-files) for a disposable render example.

The persisting-drive mount helper matches physical hardware serials exactly,
selects the unique unlocked encrypted filesystem below that device, rejects
ambiguous devices or multiple filesystem mappings and verifies the mounted block identity. It leaves filesystem
selection to the device instead of forcing ext4. Persistent secret storage must
also pass the shared encryption/swap verifier; unlock encrypted storage through
the established workflow first. A mountpoint already in use by another device
is an error, not successful setup.

## Manual recovery and provider templates

Two preserved scripts are deliberately not exposed as canonical commands:

- `hetzner-dedicated-wipe-and-install-nixos.sh` is a destructive, legacy-BIOS,
  two-disk Hetzner installation template.
- `recover-files-live-boot.sh` is a site-specific `gc-06` live-boot recovery
  template with fixed devices, subvolumes, repository path, and host target.

Their machine-readable status and required review points live in the
[manual operations catalog](https://github.com/wg-lux/luxnix/blob/main/scripts/manual-operations.yml).
Do not stream either script directly into a privileged shell. For a supported
new installation, use the `deploy-new-host` workflow from `luxnix.yml`; for
recovery, adapt a reviewed copy to the actual disks and recovery objective.

## Next steps

- Continue with [Deployment Guide](./deployment-guide.md)
- Run preflight checks from [Getting Started](./getting-started.md#preflight-checklist)
