# LuxNix Nixtests

This page documents the `technofab/nixtest` integration now exposed by the LuxNix flake.

## Entry Point

From the LuxNix repo root:

```bash
nix run .#nixtests -- --workers 1
```

The flake also exposes the derivation as:

```bash
nix build .#nixtests
```

## What It Covers

The current suite focuses on operational safety around Vault-backed `lx-annotate` deployment.

### Contract Tests

These are fast source-level checks that verify:

- Vault bootstrap service wiring exists
- `managed-secrets` includes `customSecrets`
- secret refresh and atomic replacement are enabled
- lx-annotate Vault secrets stay root-only
- lx-annotate Vault mode asserts required prerequisites

### VM Reachability Tests

These use NixOS VMs to verify:

- a secret/bootstrap failure does not make the machine unreachable over SSH
- an application service failure does not remove administrative reachability

## Why This Matters

These tests are intended to prevent two classes of outage:

- secret-management regressions that break encrypted-data boot
- security hardening changes that accidentally lock out authorized operators

## Extending The Suite

Tests live in:

- [tests/nixtest](/home/admin/dev/luxnix/tests/nixtest)

Rules of thumb:

- use script tests for static module contracts
- use VM tests only for boot order, reachability, or service-failure behavior
- keep VM tests narrow and single-purpose so failures stay attributable

Files ending with `*_test.nix` are autodiscovered by the flake.
