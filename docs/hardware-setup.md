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
nh os switch
nh home switch
```

Alias equivalents:

- `nho` -> `nh os switch`
- `nhh` -> `nh home switch`

## Password/secret path note

If your setup uses managed admin passwords, follow [Vault Setup](./vault-setup.md).
Do not rely on undocumented local paths like `etc/user-password/files`.

## Boot decryption setup

LuxNix provides an interactive
[`boot-decryption-stick` module](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/luxnix/boot-decryption-stick/default.nix).
Enable `luxnix.boot-decryption-stick`, rebuild the host, and run the generated
`boot-decryption-stick-setup` command as root.

The command can format the selected device and add a key to the LUKS volume.
Verify the device path and keep a tested recovery key before confirming either
operation.

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
