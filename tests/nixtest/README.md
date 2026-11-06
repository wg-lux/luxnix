# LuxNix Nixtests

This directory contains the `technofab/nixtest` safety suite exposed through the flake as:

```bash
nix run .#nixtests -- --workers 1
```

## Scope

The current suite covers two categories:

- `lx-annotate vault contracts`
  Checks that the LuxNix Vault, managed-secrets, and `lx-annotate-local` modules keep the expected fail-closed and root-only contracts in source.

- `vault secret delivery contracts`
  Checks that Vault runtime credential files remain root-only, managed-secrets consumes the runtime Vault environment, lx-annotate secret generators remain hostname-scoped, and the lx-annotate runtime keeps propagating encryption-related environment and mount gating.

- `reachability safety`
  Uses NixOS VMs to assert that common boot-time failures do not make the host unreachable to authorized personnel over SSH.

- `ssh host contracts`
  Evaluates the effective SSH configuration of the configured Linux hosts in the flake. It checks that SSH stays enabled with password authentication disabled, that port `22` remains the only configured SSH port, and that hosts with explicit `ssh-access.dev-*` overlays keep the expected layered admin key set while baseline hosts stay on the root/admin key only.

## Why These Tests Exist

The main operational safety goals are:

- Vault bootstrap must be explicit, not ambient.
- lx-annotate Vault-backed secrets must stay root-only.
- Secret handling must be atomic and refresh-capable.
- Application or secret bootstrap failures must not take down administrative SSH reachability.

## Adding Tests

- Add new `*_test.nix` files in this directory.
- The flake autodiscovers them into the `nixtests` package.
- Prefer fast script tests for static contracts and VM tests only for host-reachability or boot-order behavior.
