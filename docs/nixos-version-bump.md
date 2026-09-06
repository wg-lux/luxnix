# NixOS and Nixpkgs Version Bump

This runbook covers moving the flake's Nixpkgs inputs forward: a routine
refresh within the current release branch, and the larger channel bump to the
next NixOS release. Both are disruptive - they change package versions across
every exported host - so both follow the same capture, change, compare, and
gate sequence.

Do not deploy a bump straight to the fleet. Evaluate, build, and canary first.

## Vocabulary

| Term | Meaning |
| --- | --- |
| Refresh | `nix flake update nixpkgs nixpkgs-unstable` - newest commit of the *same* branch. Security patches, minor version moves. |
| Channel bump | Editing `flake.nix` to a newer release branch (for example `nixos-25.11` → `nixos-26.05`), then re-locking. Major package moves, option renames, removals. |
| State snapshot | The JSON file written by `devenv tasks run repo:state-summary`: repository revision, flake input ages, and the pass/fail of every test and per-host evaluation. |

## When to bump

- `devenv tasks run nix-quality:check` reports `flake_checker.issues` above its
  baseline in `nix-quality.yml`. flake-checker warns when an input is older
  than 30 days or when its branch is no longer supported.
- A NixOS release branch reaches end of support (roughly seven months after
  release). At that point both the "outdated" and "unsupported branch"
  warnings persist until a channel bump - a refresh cannot clear them.
- A security advisory affects a pinned package.

> **Current state:** `nixpkgs` tracks `nixos-25.11`, which has reached end of
> support. `nix-quality.yml` carries a flake-checker baseline of 2 to
> accommodate the resulting permanent warnings. Clearing them requires a
> channel bump to `nixos-26.05`; until then, keep refreshing within `25.11`
> for security patches.

## 26.05 upgrade status

The `lx/nixos-26.05` branch carries the channel bump (`nixpkgs`,
`home-manager`, `nixvim` → `nixos-26.05` / `release-26.05`) and the module
fixes 26.05 requires.

Module fixes on the branch:

- `kwalletcli` removed (Plasma 5 EOL) → dropped; `kdePackages.kwallet` covers it.
- `hardware.nvidia.package` is strictly unique in 26.05 → `luxnix.nvidia-default`
  now sets it with `mkDefault` so `luxnix.nvidia-prime` wins cleanly.
- `services.ollama.acceleration` removed → dropped; the wrapper already selects
  `ollama-<backend>` through `services.ollama.package`.
- `pgvecto-rs` removed (abandoned upstream). It was dead config: neither
  endoreg-db nor lx-annotate uses a PostgreSQL vector extension (no dependency,
  no vector columns, no `CREATE EXTENSION`), so the preloaded `vectors.so`, the
  `vectors` schema, and the extension were dropped from
  `modules/nixos/services/postgres/default.nix`.

Remaining blocker:

| Blocker | Impact | Options |
| --- | --- | --- |
| `minio` marked insecure (abandoned upstream, 6 unpatched CVEs) | `s-03` Nextcloud object store (bound to `127.0.0.1`, behind nginx) | drop the object store for local disk storage; migrate to `services.garage` (S3-compatible); or `permittedInsecurePackages` short-term. `s-03` is not running, so there is no data to migrate. |

Every host except `s-03` evaluates on 26.05 with the fixes above.

## 1. Capture the baseline

Work on a branch with a clean tree:

```bash
git switch -c chore/nixpkgs-bump
git status --short   # must be empty
devenv tasks run repo:state-summary --label before
```

`repo:state-summary` runs the repository Python suite, the ratcheted Nix
quality gate, the nixtests, and a no-build evaluation of every exported host,
then writes `repo-state/repo-state-<timestamp>-before.json` and
`repo-state/latest.json`. The `repo-state/` directory is git-ignored.

Everything that is green here is your contract for the bump: the change must
not regress it. If something is already red, record why before continuing so
the post-bump comparison is not misread.

For the stricter baseline that also does a no-link build of every host and a
full `nix flake check`, use `--all` (slow; needs a warm cache):

```bash
devenv tasks run repo:state-summary --all --label before-full
```

## 2. Apply the bump

### Refresh (same branch)

```bash
nix flake update nixpkgs nixpkgs-unstable
```

### Channel bump (new release)

1. Edit `flake.nix`:

   ```nix
   nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
   ```

   Leave `nixpkgs-unstable` on `nixos-unstable`.

2. Re-lock:

   ```bash
   nix flake update nixpkgs nixpkgs-unstable
   ```

3. Read the release notes for the target version and grep the tree for every
   removed or renamed option the notes list (`rg 'services\.<name>'`,
   `modules/`, `systems/`, `homes/`). Fix them in the modules and in the
   Jinja templates under `conf/nix-templates/`, not in generated host files.

4. Regenerate the generated configuration:

   ```bash
   devenv tasks run autoconf:generate
   ```

## 3. Compare

```bash
devenv tasks run repo:state-summary --label after
```

Diff the two snapshots:

```bash
git -c core.pager=cat diff --no-index \
  repo-state/repo-state-*-before.json repo-state/repo-state-*-after.json || true
```

Read, in order:

- `repository_state.flake_inputs` - the new revisions and ages; `age_days`
  should drop and `outdated` should clear for a refresh.
- `repository_state.flake_checker_issue_count` - must be at or below the
  `nix-quality.yml` baseline.
- `totals` and any `checks[].status` that moved from `passed` to `failed` -
  every regression must be understood and fixed before deploying. A check
  that was already failing in the `before` snapshot is not introduced by the
  bump, but say so explicitly in the change description.

Fix regressions, re-run `repo:state-summary --label after`, and repeat until
the `after` snapshot matches or improves on `before`.

## 4. Gate before deploying

1. Full evaluation and no-link build of every host:

   ```bash
   ./tests/run-configuration-tests.sh
   ```

   or `devenv tasks run repo:state-summary --all --label after-full`.

2. Deploy to one non-critical canary host and verify:

   ```bash
   sudo nixos-rebuild rollback   # know the escape hatch first
   systemctl --failed
   journalctl -p err -b
   ```

3. Only then roll the remaining hosts, in small batches, checking
   `systemctl --failed` on each.

## Rollback

Before activation, discard the bump entirely:

```bash
git checkout -- flake.nix flake.lock
```

After activation on a host, roll that host back to its previous generation:

```bash
sudo nixos-rebuild rollback
```

Never delete input paths directly from `/nix/store`; let the generation
history and `nix-collect-garbage` manage them.

## Commit

Commit `flake.nix` (channel bump only), `flake.lock`, any module or template
fixes, and any regenerated host files together. Reference the before/after
snapshot totals in the message. Do not commit the `repo-state/` snapshots -
they are local evidence.
