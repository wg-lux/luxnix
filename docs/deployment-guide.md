# Deployment Guide

This guide describes how to deploy a LuxNix host with current repository tooling.

For a first-time setup flow, start with [Getting Started](./getting-started.md).

## Scope

- Example host names: `gc-02`, `s-02`, etc.
- Deployment method: `nixos-anywhere`
- Control machine: host where this repository is cloned

## Prerequisites

- Nix + flakes enabled on the control machine
- `nixos-anywhere` available on the control machine
- SSH keypair on control machine (`~/.ssh/id_ed25519` by default)
- Target machine booted into NixOS installer
- Host config exists under `systems/x86_64-linux/<host>/`

## 1. Prepare target machine (NixOS installer)

On target machine:

```bash
passwd
ip a
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

On control machine, copy your key if needed:

```bash
cat ~/.ssh/id_ed25519.pub
```

Verify SSH access from control machine:

```bash
ssh nixos@<target-ip>
```

## 2. Prepare host configuration

On the control machine:

1. Ensure these files exist:
   - `systems/x86_64-linux/<host>/default.nix`
   - `systems/x86_64-linux/<host>/disks.nix`
   - `systems/x86_64-linux/<host>/hardware-configuration.nix`
   - `homes/x86_64-linux/admin@<host>/default.nix`
2. If generating hardware config from installer output, copy only relevant hardware fields.
3. Confirm disk identifiers in `disks.nix` match target hardware.

## 3. Optional: bootstrap vault/secrets

If your host relies on managed secrets:

```bash
# Create local password mapping from tracked example
cp ansible/admin-passwords.example.yml ansible/secrets/admin-passwords.yml

# Build autoconf outputs (including autoconf/inventory.yml)
devenv tasks run autoconf:finished

# Bootstrap vault and export per-host encrypted secrets
devenv run vault-bootstrap -- \
  --inventory ./autoconf/inventory.yml \
  --admin-passwords ansible/secrets/admin-passwords.yml \
  --export
```

Validate admin passwords (optional):

```bash
devenv run validate-admin-passwords -- \
  --vault-dir ~/.lxv \
  --vault-key ~/.lxv.key \
  --admin-passwords ansible/secrets/admin-passwords.yml
```

## 4. Preflight checks

Run before deployment:

```bash
# Host evaluates
nix eval ".#nixosConfigurations.<host>.config.system.build.toplevel.drvPath"

# Host builds
nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link

# Connectivity via Ansible inventory
./scripts/check-connectivity.sh <host>
```

Optional full validation for all configured hosts:

```bash
./tests/run-configuration-tests.sh
```

## 5. Deploy with nixos-anywhere

```bash
nixos-anywhere --flake ".#<host>" nixos@<target-ip>
```

## 6. Post-install on target host

```bash
# Canonical commands
nh os switch
nh home switch

# Aliases (if enabled)
# nho
# nhh
```

If using boot decryption stick setup, continue in [Security](./security.md#boot-decryption-usb-stick-setup).

## 7. Add a new host checklist

1. Add system directory: `systems/x86_64-linux/<host>/`
2. Add home config: `homes/x86_64-linux/admin@<host>/default.nix`
3. Add host to `ansible/inventory/hosts.ini`
4. Add/update `ansible/inventory/host_vars/<host>.yml` as needed
5. Run `devenv tasks run autoconf:finished`
6. Run preflight checks
7. Deploy with `nixos-anywhere`

## Notes on old commands in historical docs

Older docs may reference scripts such as `deploy-authorized-key.sh` or `deploy-openvpn-certificates*.sh`. Those scripts are not present in this repository; use the flow above.
