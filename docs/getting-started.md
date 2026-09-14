# Getting Started

This guide is the canonical Day-0 onboarding path for new LuxNix users.

For a concise, machine-readable index of repository paths and commands, see
[`luxnix.yml`](https://github.com/wg-lux/luxnix/blob/main/luxnix.yml). Its workflow risk labels distinguish read-only
inspection from local-state and remote deployment operations.

## Who this is for

- You are installing or reprovisioning a LuxNix host.
- You have SSH access from a control machine to the target.
- You want one reliable path from clone to first successful deploy.

## Components you need

- `luxnix` repository (this repository)
- Nix with flakes enabled on the control machine
- Devenv for cataloged tasks and shell wrappers
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
3. Select and configure the target hostname:
   - Discover existing exported hosts with
     `nix eval --json '.#nixosConfigurations' --apply builtins.attrNames`.
   - For a new remote host, add it to `ansible/inventory/hosts.ini`, including
     the appropriate inventory groups, and add its durable values below
     `ansible/inventory/host_vars/<host>.yml`.
   - Put shared values below `ansible/inventory/group_vars/`; its `README.md`
     documents ownership and load order.
   - When Home Manager is needed, add the host to
     `ansible/inventory/home-hosts.yml` and add its values below
     `ansible/inventory/host_vars/home/<host>.yml`.
4. Validate and generate the derived configurations:
   - `devenv tasks run autoconf:check`
   - `devenv tasks run autoconf:generate`
   - Review `systems/x86_64-linux/<host>/default.nix` and the optional generated
     home entry; do not edit either output directly.
   - Add or verify adjacent `disks.nix` and `hardware-configuration.nix` only
     when the generated system entry point imports them. See
     [Hardware Setup](./hardware-setup.md).
5. Run preflight checks:
   - `nix eval '.#nixosConfigurations.<host>.config.system.build.toplevel.drvPath'`
   - `nix build '.#nixosConfigurations.<host>.config.system.build.toplevel' --no-link`
   - `devenv shell check-connectivity <host>`
6. Prepare the admin credential using the canonical
   [Admin Password Creation and Rotation](admin-passwords.md) guide:
   - Create, import, validate and export the host's unique password/hash pair.
   - Stage the protected runtime hash for first activation as described under
     [Install on a new machine](admin-passwords.md#6-install-on-a-new-machine).
7. Deploy after explicitly confirming the target and destructive install scope:
   - `nixos-anywhere --extra-files <staging-root> --flake '.#<host>' nixos@<target-ip>`
   - Use the verified staging tree from the admin password guide; the hash must
     exist before first activation.
8. First login on target host:
   - `nh os switch` (alias: `nho`)
   - `nh home switch` (alias: `nhh`)

At each boundary, record the selected host, repository commit, `flake.lock`
revision, and command output. Do not continue when inventory generation,
evaluation, build, connectivity, or SSH host-key verification fails.

## Preflight checklist

Run these before a production deploy:

- Host exists in flake outputs:
  - `nix eval --json '.#nixosConfigurations' --apply builtins.attrNames`
- Target reachable over SSH:
  - `devenv shell check-connectivity <host>`
- Optional full-repo config validation:
  - `./tests/run-configuration-tests.sh`

## Canonical vs aliases

Always use canonical commands in documentation and runbooks:

- OS switch: `nh os switch` (alias: `nho`)
- Home switch: `nh home switch` (alias: `nhh`)
- GC: `nix-collect-garbage -d` (alias: `cleanup`)

## If deployment fails

- Start with [Common Errors](https://github.com/wg-lux/luxnix/blob/main/CommonErrors.md).
- Then review:
  - `logs/connectivity-*.log`
  - `tests/eval-logs/*.log`

For an installer failure, leave the target in the installer, preserve the
`nixos-anywhere` output, and re-check disk and hardware inputs before retrying.
For an activation failure on an existing installation, select the previous
NixOS generation at boot or run `sudo nixos-rebuild switch --rollback`, then
verify SSH, `/run/current-system`, mounts, and critical services. Restore
host-specific files from the approved backup if required, regenerate from the
canonical inventory, and repeat all preflight checks before deployment. Treat
the procedure as incomplete until those checks pass.
