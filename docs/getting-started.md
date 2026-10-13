# Getting Started

Use this guide to prepare and install a LuxNix host. You can also inspect an
existing configuration locally before deciding whether to deploy it.

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

## Read command examples

Run control-machine commands from the repository root. Replace values in angle
brackets before running a command; do not paste the brackets literally.

| Value | How to choose it |
| --- | --- |
| `<host>` | A host returned by the discovery command below, matching the intended machine |
| `<target-ip>` | The independently confirmed address of that machine in the installer |
| `<staging-root>` | The protected directory prepared by the admin password installation guide |

A **flake** is the repository's Nix entry point; `flake.lock` records its pinned
dependencies. **Inventory** is the host and group data under `ansible/inventory/`.
**Autoconf** turns that data and templates into configuration files.
**Activation** applies a built configuration to a machine.

## Inspect an existing host locally

With Nix and flakes enabled, run:

```bash
nix eval --json '.#nixosConfigurations' --apply builtins.attrNames
```

Expect a JSON list of host names. For a local evaluation or build of an existing
configuration, choose one and use the commands in step 5 below, replacing
`<host>`. If you change inventory inputs first, validate and regenerate them as
shown in step 4. Stop after evaluation and build if you only want to inspect the
configuration; connectivity checks and subsequent steps concern deployment.

## Install a host

The following steps can replace the target's operating system and partition its
disks. Confirm backups, recovery access, the selected host and address, and the
reviewed repository revision before installation. For local development only,
continue with [Development](development.md).

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

   Evaluation should print a `/nix/store/…drv` path. A successful build exits
   with status zero; `--no-link` creates no `result` link. Evaluation and build
   may download dependencies or populate the local Nix store, but do not
   activate the configuration. The connectivity check contacts the target and
   must succeed before deployment.

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
   - `sudo nixos-rebuild switch --flake '.#<host>'` (alias: `nho`)
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

- OS switch: `sudo nixos-rebuild switch --flake '.#<host>'` (alias: `nho`)
- Stage next boot without live activation: `sudo nixos-rebuild boot --flake '.#<host>'` (alias: `nhb`)
- Update inputs only: `nix flake update --flake <checkout>` (alias: `nhu`)
- Home switch: `nh home switch` (alias: `nhh`)
- GC: `nix-collect-garbage -d` (alias: `cleanup`)

Rebuild aliases require `LUXNIX_FLAKE` and `LUXNIX_HOST`; they do not use `nh`'s
temporary activation. Follow the [SSH deployment checks](deployment-guide.md#ssh-access-during-updates)
and retain console recovery for changes that could break remote access.

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
