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

## 3. Optional: bootstrap vault/secrets

If your host relies on managed secrets:

```bash
# Create local password mapping from tracked example
mkdir -p ansible/secrets
cp ansible/admin-passwords.example.yml ansible/secrets/admin-passwords.yml

# Bootstrap vault and export per-host encrypted secrets
devenv shell vault-bootstrap \
  --admin-passwords ansible/secrets/admin-passwords.yml \
  --export
```

Validate admin passwords (optional):

```bash
devenv shell validate-admin-passwords \
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
devenv shell check-connectivity <host>
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

If using a boot decryption stick, continue with
[Hardware Setup](./hardware-setup.md#boot-decryption-setup).

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
