# Configuration and Nixtest Suites

LuxNix has two complementary Nix configuration entry points. Use the repository
configuration suite for every exported host and Nixtests for focused safety and
VM contracts.

## Repository configuration suite

Run the full host evaluation and build loop from the repository root:

```bash
./tests/run-configuration-tests.sh
```

The script discovers every `nixosConfigurations` output, evaluates each host,
and builds it with `--no-link` without activating it. It continues after
per-host failures, returns nonzero when any host fails, and writes diagnostic
output below `tests/eval-logs/`. The build phase has an 80-second timeout per
host, so a timeout can indicate a large derivation or unavailable cache rather
than an evaluation error.

## Nixtest entry point

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

- [`tests/nixtest`](https://github.com/wg-lux/luxnix/tree/main/tests/nixtest)

Rules of thumb:

- use script tests for static module contracts
- use VM tests only for boot order, reachability, or service-failure behavior
- keep VM tests narrow and single-purpose so failures stay attributable

Files ending with `*_test.nix` are autodiscovered by the flake.
