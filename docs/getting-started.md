# Getting Started

This guide is the canonical Day-0 onboarding path for new LuxNix users.

## Who this is for

- You are installing or reprovisioning a LuxNix host.
- You have SSH access from a control machine to the target.
- You want one reliable path from clone to first successful deploy.

## Components you need

- `luxnix` repository (this repository)
- Nix with flakes enabled on the control machine
- `nixos-anywhere` available on the control machine
- SSH keypair on the control machine (default: `~/.ssh/id_ed25519`)

Notes:
- The Python admin package is part of this repository as `lx_administration/`.
- Older docs may mention `luxnix_administration`; use `lx_administration`.

## Day-0 flow

1. Prepare the target machine in the NixOS installer:
   - Set a temporary password: `passwd`
   - Get IP address: `ip a`
   - Add your control-host public key to `~/.ssh/authorized_keys`
2. Clone LuxNix on the control machine:
   - `git clone https://github.com/wg-lux/luxnix.git`
   - `cd luxnix`
3. Select the target hostname:
   - Choose an existing host from `systems/x86_64-linux/` or create a new one.
4. Ensure host files exist:
   - `systems/x86_64-linux/<host>/default.nix`
   - `systems/x86_64-linux/<host>/disks.nix`
   - `systems/x86_64-linux/<host>/hardware-configuration.nix`
   - `homes/x86_64-linux/admin@<host>/default.nix`
5. Run preflight checks:
   - `nix eval ".#nixosConfigurations.<host>.config.system.build.toplevel.drvPath"`
   - `nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link`
   - `./scripts/check-connectivity.sh <host>`
6. Bootstrap inventory and vault (if secrets are needed):
   - `cp ansible/admin-passwords.example.yml ansible/secrets/admin-passwords.yml`
   - `devenv tasks run autoconf:finished`
   - `devenv run vault-bootstrap -- --inventory ./autoconf/inventory.yml --admin-passwords ansible/secrets/admin-passwords.yml --export`
7. Deploy:
   - `nixos-anywhere --flake ".#<host>" nixos@<target-ip>`
8. First login on target host:
   - `nh os switch` (alias: `nho`)
   - `nh home switch` (alias: `nhh`)

## Preflight checklist

Run these before a production deploy:

- Host exists in flake outputs:
  - `nix eval --json --expr 'builtins.attrNames (builtins.getFlake (toString ./.)).nixosConfigurations' | jq -r '.[]'`
- Target reachable over SSH:
  - `./scripts/check-connectivity.sh <host>`
- Optional full-repo config validation:
  - `./tests/run-configuration-tests.sh`

## Canonical vs aliases

Always use canonical commands in documentation and runbooks:

- OS switch: `nh os switch` (alias: `nho`)
- Home switch: `nh home switch` (alias: `nhh`)
- GC: `nix-collect-garbage -d` (alias: `cleanup`)

## If deployment fails

- Start with [CommonErrors](../CommonErrors.md).
- Then review:
  - `logs/connectivity-*.log`
  - `tests/eval-logs/*.log`
