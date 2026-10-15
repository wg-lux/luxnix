# Deployment Guide

This guide describes how to deploy a LuxNix host with current repository tooling.

For a first-time setup flow, start with [Getting Started](./getting-started.md).

## Scope

- Example host names: `gc-02`, `s-02`, etc.
- Deployment method: `nixos-anywhere`
- Control machine: host where this repository is cloned

## Production Source And Temporary-File Policy

LuxNix is a fleet repository: shared modules and defaults can affect every
clinical-network host, even when a command names only one target. A production
deployment must therefore be built from an attributable, reviewable source.

Use a long-lived LuxNix clone or a deliberately retained release worktree as the
deployment source. Before evaluating or switching a host:

1. Confirm the repository path and target host explicitly.
2. Record `git rev-parse HEAD`, the selected branch or tag, and the `flake.lock`
   revision with the deployment evidence.
3. Review `git status --short`; do not deploy unrelated or unexplained changes.
4. Run evaluation and build from the same source path that will be deployed.
5. Run the host acceptance checks after activation and retain their logs.

Do not use any of the following as a production Flake or repository source:

- an untracked checkout or Git worktree below `/tmp`;
- a copied repository whose commit and local changes are not recorded;
- a generated render directory, test fixture, cache, or verification clone;
- a temporary safety override that has not been incorporated into the reviewed
  production configuration.

Temporary directories are appropriate for disposable build output, rendered
configuration, test environments, and short-lived artifact staging. They are
not runtime dependencies and must not become an operator's source of truth.
Secrets, clinical data, and durable audit evidence must never be stored there.

### Release Worktrees

A release worktree is justified when it provides a stable, named and reviewable
release boundary while other development continues. Keep it outside `/tmp`,
attach it to a named branch or tag, and require a clean status before deployment.
Remove it when the release is superseded and all unique commits are preserved by
a durable Git reference. A worktree created only to render, build, or test one
candidate has no continuing production need after acceptance.

### Post-Deployment Cleanup

After acceptance succeeds:

1. Verify `/run/current-system` and the relevant service `ExecStart` paths. The
   active NixOS generation must resolve to `/nix/store`, not to a temporary
   checkout.
2. Confirm that no live process references the candidate's temporary paths.
3. Remove registered temporary worktrees with `git worktree remove`, then run
   `git worktree prune` in the owning repository.
4. Remove disposable wheels, virtual environments, render output, caches, and
   diagnostic response bodies according to the host's temporary-file policy.
5. Remove an extra temporary GC root only after another durable root, such as
   `/run/current-system` or a system profile generation, protects the selected
   closure. Never delete paths directly from `/nix/store`.

Prefer a recoverable quarantine when the contents have not yet been independently
verified. Preserve structured deployment and acceptance logs, but move them to
the approved audit-log location rather than leaving them in `/tmp`.

## Updating an existing LX-Annotate host

Use `nixos-rebuild switch` for a persistent live update after the source, build,
connectivity, and target checks above. Run on the explicitly selected host from
the reviewed checkout; for gc-10:

```bash
sudo nixos-rebuild switch --flake .#gc-10
readlink -e /run/current-system
readlink -e /nix/var/nix/profiles/system
systemctl --failed
systemctl is-active lx-annotate.service
```

Require a successful rebuild and equal active/system-profile paths before
declaring deployment successful. Equality alone does not prove the firmware's
boot selection: check the bootloader default and any one-shot override, then
verify `/run/booted-system` matches the intended closure after a scheduled reboot.
The managed Ansible handler checks active/profile equality after switching.

For kernel or NVIDIA driver changes that cannot be activated safely live, use
`sudo nixos-rebuild boot --flake .#gc-10` and reboot in an authorized maintenance
window. The running generation is expected to differ until that reboot.

Do not use `nixos-rebuild test` on wheel-mode LX-Annotate production hosts.
Their pre-switch check rejects this action before activation, including helpers
that internally perform `test` before persisting the boot generation. Use
`nixos-rebuild build` or `dry-activate` for non-activating review instead.
The shell alias `nho` now invokes native `nixos-rebuild switch`; `nhb` stages
with `nixos-rebuild boot` without restarting running services. Both require
`LUXNIX_FLAKE` and `LUXNIX_HOST` to select the reviewed checkout and host explicitly.
`nhu` only updates that checkout's flake lock; review and build before activation.
Existing shells retain their old aliases until Home Manager is applied and a
new shell is opened. Use the explicit command above for the first deployment.
See the [NixOS switching documentation](https://github.com/NixOS/nixpkgs/blob/master/nixos/doc/manual/development/what-happens-during-a-system-switch.chapter.md).

### SSH access during updates

Run `devenv shell check-connectivity gc-10` from the controller before changing
gc-10. Keep the original SSH session open, then verify a second fresh connection
with host-key verification enabled after activation. The managed Ansible handler
closes its cached connection and requires a fresh authenticated connection before
continuing. A successful rebuild or an existing SSH session alone is insufficient.

The pinned NixOS SSH module uses `stopIfChanged = false` and `KillMode = "process"`
to preserve established SSH child sessions during daemon replacement. These
settings do not preserve a broken VPN route, firewall policy, or authentication
configuration. Keep key-only authentication and pinned host identity checks.

No rebuild command guarantees SSH after arbitrary failures. For changes to SSH,
VPN, firewall, kernel, or boot configuration, stage with `nhb` and arrange console
or out-of-band recovery before the separately authorized reboot. Staging leaves
the current running SSH configuration in place; it does not prove the next boot
will be reachable. Do not attach an automatic generation rollback to these
stateful application deployments: it cannot roll back database or shared-runtime
mutations. A failed activation requires inspection, not an automatic reboot.

On gc-10, an October 8, 2026 `test` activation installed LX-Annotate 1.4.9,
while the persisted generation retained 1.3.12. The October 12 reboot exposed
this mismatch and the downgrade guard stopped startup. The activation log does
not establish whether `test` was requested directly or invoked by a helper.

NixOS generation rollback does not restore the shared virtualenv or database.
For these hosts, the rollback suggestions elsewhere in this guide require an
independently verified compatible application/database pair. Preserve the
downgrade and migration checks; recover using a reviewed compatible persistent
generation. Older generations do not acquire this new pre-switch check.

## Prerequisites

- Nix + flakes enabled on the control machine
- `nixos-anywhere` available on the control machine
- SSH keypair on control machine (`~/.ssh/id_ed25519` by default)
- Target machine booted into NixOS installer
- Existing host inputs are present in the Ansible inventory, or you are ready
  to add them in the next section.

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

1. Add a new remote target to `ansible/inventory/hosts.ini` and its appropriate
   inventory groups. Existing hosts should already be present there.
2. Put durable host values in `ansible/inventory/host_vars/<host>.yml` and
   shared defaults below `ansible/inventory/group_vars/`.
3. When Home Manager is needed, add the host to
   `ansible/inventory/home-hosts.yml` and its values below
   `ansible/inventory/host_vars/home/<host>.yml`. A Home-only host does not need
   a fake remote inventory entry.
4. Run `devenv tasks run autoconf:check`, then
   `devenv tasks run autoconf:generate`.
5. Review the generated outputs without editing them directly:
   - `systems/x86_64-linux/<host>/default.nix`: Required for every exported
     NixOS host configuration.
   - `homes/x86_64-linux/<user>@<host>/default.nix`: Required only when the host
     has a Home Manager configuration.
6. Inspect the system entry point's imports and add only the adjacent files the
   selected host needs:
   - `disks.nix`: Required when the host entry point imports it for a disko-based installation.
   - `hardware-configuration.nix`: Required only when the host entry point imports generated hardware configuration.
7. If the entry point imports generated hardware configuration, copy only the
   relevant fields from the installer output into `hardware-configuration.nix`.
8. If the entry point imports `disks.nix`, confirm its disk identifiers match
   the target hardware.

## 3. Prepare managed admin credentials

Follow [Admin Password Creation and Rotation](admin-passwords.md) for private
input creation, paired import, mandatory validation and encrypted export.
For a new installation, follow its runtime-hash staging procedure before first
activation. A missing hash fails activation; no shared fallback is installed.
For an existing account, use its scoped rotation workflow and acceptance checks.

## 4. Preflight checks

Run before deployment:

```bash
# Host evaluates
nix eval ".#nixosConfigurations.<host>.config.system.build.toplevel.drvPath"

# Host builds
nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link

# Connectivity via Ansible inventory
devenv shell check-connectivity <host>
```

Optional full validation for all configured hosts:

```bash
./tests/run-configuration-tests.sh
```

Record the evaluation, build, connectivity, and hardware checks before
continuing. If any check fails, stop, correct the canonical inventory or
template input, regenerate, and repeat the preflight; do not start an
installer deployment from a failed or stale result.

## 5. Deploy with nixos-anywhere

Use the protected staging tree from the [admin password guide](admin-passwords.md#6-install-on-a-new-machine).
Confirm the exact target and destructive install scope before running:

```bash
nixos-anywhere --extra-files <staging-root> --flake ".#<host>" nixos@<target-ip>
```

### Deployment failure and recovery

If `nixos-anywhere` fails, preserve its output and do not retry blindly. Keep
the target in the installer until the disk and boot state are understood;
check the target console and SSH reachability, then compare the selected
hardware and `disks.nix` inputs with the real machine. A partially installed
target must be reinstalled from the reviewed flake or restored from the
operator's approved host backup before it is treated as deployed. Re-run the
evaluation, build, connectivity check, and post-install acceptance checks
after recovery. For an already running host, use the booted previous NixOS
generation from the boot menu or `sudo nixos-rebuild switch --rollback` and
verify `/run/current-system` and SSH access before retrying.

## 6. Post-install on target host

```bash
# Canonical commands
sudo nixos-rebuild switch --flake .
nh home switch

# Aliases (if enabled)
# nho
# nhh
```

If using a boot decryption stick, continue with
[Hardware Setup](./hardware-setup.md#boot-decryption-setup).

Validate the active generation, SSH access, expected mounts, and critical
services before cleanup. If activation or acceptance fails, retain the failed
generation and logs, boot or switch to the previous known-good generation,
restore any host-specific files from the approved backup, and repeat the
preflight before another activation. Do not remove temporary worktrees or GC
roots until recovery is no longer needed.

## 7. Add a new host checklist

1. Add the remote target to `ansible/inventory/hosts.ini` and the appropriate
   inventory groups.
2. Add durable host inputs below `ansible/inventory/host_vars/<host>.yml` and
   shared defaults below `ansible/inventory/group_vars/`.
3. When an admin Home Manager configuration is needed, add the host to
   `ansible/inventory/home-hosts.yml` and its values below
   `ansible/inventory/host_vars/home/<host>.yml`.
4. Add deliberately hand-maintained disk, boot, or hardware files beside the
   system entry point only when its imports require them.
5. Run `devenv tasks run autoconf:check`, then
   `devenv tasks run autoconf:generate`.
6. Review generated outputs without editing them directly. Correct their
   Inventory, template, or Autoconf inputs instead.
7. Run the preflight checks and deploy with `nixos-anywhere` only after they
   pass.

### Study laptops that send to the central hub

A study laptop is not hub-ready merely because its base NixOS configuration
boots. After completing the host checklist, follow
[Add a Machine to Vault-Backed Hub Transfer](./vault-hub-machine-enrollment.md)
in full. That runbook covers both sides of the declarative `NetworkNode`
configuration, Vault AppRole enrollment, mTLS, the per-site request secret, the
hub X25519 envelope-recipient key, local storage master-key separation,
deployment order, acceptance checks, a disposable transfer, and the controlled
first Django-superuser bootstrap on `gs-02`.

Do not copy credentials from another `gc-*` host. Every site has its own
AppRole identity, mTLS private key, and request-authentication secret. Only the
hub's public X25519 recipient key and public CA certificates are distributed;
the hub recipient private key, Vault unseal shares, and each node's application
master key remain inside their respective security boundaries.

## Notes on old commands in historical docs

Older docs may reference scripts such as `deploy-authorized-key.sh` or `deploy-openvpn-certificates*.sh`. Those scripts are not present in this repository; use the flow above.
