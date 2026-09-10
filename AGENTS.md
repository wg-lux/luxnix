# LuxNix Agent and Contributor Guide

LuxNix is a security-focused NixOS configuration repository for reproducible
multi-host deployments. Treat this repository as infrastructure code: a small
change to a shared module, inventory variable, template, or secret contract
may affect more than the host currently being inspected.

## Start here

Before making a change, read the relevant entries in this order:

1. [`luxnix.yml`](luxnix.yml), the machine-readable project map, path
   ownership map, risk vocabulary, and canonical workflows.
2. [`devenv/commands.yml`](devenv/commands.yml), for supported shell wrappers
   and tasks.
3. The relevant guide under [`docs/`](docs/index.md), especially Architecture,
   Autoconf, Deployment, and Testing.
4. The feature-tracking YAML and its [`README`](feature-tracking/README.md)
   when the work belongs to a tracked cleanup or readiness feature.

Do not infer ownership or deployment behavior from filenames alone. Inspect
actual imports, inventory precedence, templates, call sites, tests, and
documentation before editing.

## Working agreement

Before editing:

- Inspect the relevant files, generated status, and `git status --short`.
- Identify canonical inputs, derived outputs, consumers, tests, and ownership
  boundaries.
- State the exact files intended to change and the files deliberately left
  untouched for non-trivial work.
- Preserve unrelated user changes. Never reset, discard, or overwrite them.

During implementation:

- Keep the change minimal and directly tied to the request.
- Prefer existing modules, wrappers, helpers, tasks, and tests over one-off
  mechanisms.
- Do not add placeholders, fake secrets, fake API keys, mock production data,
  or silent fallbacks unless explicitly required.
- Fail loudly when configuration is inconsistent; do not hide errors to make
  evaluation or deployment continue.
- Keep documentation and comments in English.
- Prefer editing canonical YAML inputs and templates; do not hand-edit
  generated Nix output when a generator owns it.

After implementation, run the narrowest relevant checks first, then broader
checks when module, generator, deployment, or security boundaries were crossed.
Report exact commands and results, including failures and residual risk.

## Canonical ownership and generated files

- Host entry points live under `systems/x86_64-linux/<host>/`.
- Home Manager entry points live under `homes/x86_64-linux/<user>@<host>/`.
- Reusable NixOS modules belong under `modules/nixos/`; Home Manager modules
  belong under `modules/home/`.
- Autoconf inputs are inventories, `autoconf/config.yml`, and templates under
  `conf/nix-templates/`. Generated inventory and host/home Nix files must be
  regenerated with the documented Autoconf workflow.
- `TABLE_OF_CONTENTS.md` is derived: change `mkdocs.yaml`, then regenerate it.
- Local facts under `ansible/cmdb/` and generated reports are local-sensitive
  artifacts and must not be committed.
- Check `nix-quality.yml` for generated-file exclusions and ratcheted quality
  baselines before interpreting lint results.

When adding or changing a package:

1. Put shared contributor tooling in
   `modules/nixos/roles/custom-packages/default.nix`, normally in
   `baseDevelopment`.
2. Put a package in a service module only when it is a hard runtime dependency.
3. Put host-only tooling in `systems/x86_64-linux/<host>/default.nix`.
4. Avoid duplicate package definitions across roles and hosts.

## Nix and configuration validation

Use canonical commands from the repository root. Replace placeholders with a
known host discovered from the flake; never run a literal placeholder.

```bash
nix eval --json '.#nixosConfigurations' --apply builtins.attrNames
nix eval '.#nixosConfigurations.<host>.config.system.build.toplevel.drvPath'
nix build '.#nixosConfigurations.<host>.config.system.build.toplevel' --no-link
devenv tasks run nix-quality:check
devenv tasks run nix-quality:generators
devenv tasks run nix-quality:full
./tests/run-configuration-tests.sh
```

Use `devenv tasks run autoconf:check` before generation and
`devenv tasks run autoconf:generate` only when generated files are intended to
change. For generator work, render into a new directory outside the repository
and compare results before replacing tracked output. Never raise a quality
baseline merely to make a check pass.

## Secrets, identity, and sensitive data

- Never commit plaintext production secrets, private keys, tokens, passwords,
  local inventory facts, or rendered secret files.
- Treat SOPS files, Vault configuration, Ansible variables, host facts, and
  generated reports as sensitive according to their documented lifecycle.
- Never print secret values in logs, test output, diffs, shell traces, or docs.
- A propagated path or environment variable is only a handle. Verify that the
  referenced secret exists, has the expected format and permissions, and is
  cryptographically appropriate before declaring a service configured.
- Do not weaken encryption, host identity checks, TLS/mTLS, access controls, or
  secret ownership to unblock local development.
- Preserve encrypted-at-rest and least-privilege boundaries.

For secret bootstrap, validation, or deployment, use documented Devenv
wrappers and require operator confirmation for sensitive state changes:

```bash
devenv shell validate-admin-passwords
devenv shell vault-bootstrap
devenv shell sync-secrets --limit <host-or-group>
```

Review the command catalog and documentation first; do not substitute ad-hoc
`scp`, plaintext environment files, or hand-written remote commands.

## Deployment and destructive operations

Classify commands using the risk levels in `luxnix.yml`. Read-only evaluation
and local builds are not equivalent to activation or remote deployment.

- Confirm the exact host, address, flake revision, locked inputs, and intended
  scope before any remote-state command.
- Run `devenv shell check-connectivity <host-or-group>` before remote changes.
- Use the documented Ansible and deployment workflows rather than bypassing
  inventory and host safeguards.
- Use `nixos-anywhere` only after the Getting Started checklist and explicit
  confirmation of the target; it may repartition the target.
- Treat shared modules, defaults, group variables, and secrets as fleet-impacting.
- Review `scripts/manual-operations.yml` before reproducing a preserved
  high-risk operation.
- Never use a temporary checkout, test environment, cache, or verification
  clone below `/tmp` as a production source.

Do not run `sudo nixos-rebuild switch`, `nixos-anywhere`, Ansible state changes,
secret synchronization, disk formatting, mounts, or cleanup commands unless
the user explicitly requested that operational action and the target is
unambiguous.

## Feature tracking and agent coordination

When `feature-tracking/tracker.py` exists, choose one stable agent ID for the
entire Codex process. Use that exact ID for locks and messages. At task start
and immediately after acquiring a lock, run:

```bash
./feature-tracking/tracker.py message inbox --owner <agent-id>
```

Before releasing a feature lock, acknowledge every message acted upon and
reply with exact verification results or blockers. Never acknowledge feedback
that was not reviewed or acted upon. Use feature locks for overlapping tracked
work and inspect the applicable YAML before changing its state.

Feature tracking is evidence, not approval. Validate the tracker after related
changes:

```bash
./feature-tracking/tracker.py validate
./feature-tracking/tracker.py check <feature-id>
```

Only mark a feature done after every required criterion has stable, reviewable
evidence and an identified assessor. A nonzero readiness check is a blocker,
not a reason to weaken a criterion.

## Documentation and handoff

Documentation is part of the implementation when behavior, operations,
ownership, or risk changes. Keep canonical guidance in `docs/` and structured
workflow data in the relevant `.yml` files. After documentation changes run:

```bash
devenv tasks run docs:check
devenv tasks run docs:toc-generator   # when mkdocs navigation changed
```

The final handoff should name changed files, verification performed, anything
not run and why, deployment or security implications, and remaining blockers.
