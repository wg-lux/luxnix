# Agent context

Start at `structure.yml` in the repository root. It routes work to inventory
and deployment (`ansible`), generation options and templates (`autoconf`,
`conf`), reusable modules (`modules`), host and home outputs (`systems`,
`homes`), Python libraries (`lx_administration`), deployment resources
(`packages`, `kubernetes`, `lib`), and contributor tooling and evidence
(`devenv`, `scripts`, `tests`, `docs`, `feature-tracking`). `wg-lux-mcp` is an
independent read-only service with its own dependency lock and test environment.

The module branch splits into NixOS and Home Manager, with a dedicated
LX-Annotate deployment manifest. The Python branch splits at Autoconf, vault
models and storage. Trivial folders such as overlays, shells, topology and tmux
use root entrypoints rather than additional manifests. Preserved autodocs and
release provenance also have root entrypoints; local facts and media payloads
are not context inputs.

## Read and write protocol

Read the root summary, select the relevant child, and repeat until reaching the
owning boundary. Inspect its entrypoints, contracts and declared dependencies;
search within that tree to locate implementation details. Manifests complement
`luxnix.yml` ownership and risk metadata and `devenv/commands.yml` workflows;
they do not replace those sources or actual code contracts.

Every file addition, removal, rename or boundary change requires reviewing and
updating the owning manifest in the same changeset. List architectural
entrypoints and interfaces, not every leaf file. Add a manifest only for a
major domain, isolated service or discrete library; link it from its parent
and point its `parent` back to that manifest. Preserve custom metadata.

When delegation is authorized, give each subagent the local manifest, a bounded
directory tree, relevant contracts and explicit allowed dependency crossings.
The local manifest provides a route back to root context without dumping the
whole repository. Coordinate overlapping edits using the existing tracker.

## Schema and path conventions

All manifests use version 1 and require `tier`, `path`, `parent`, `summary`,
`responsibilities`, `boundaries`, `entrypoints`, `dependencies`, `submodules`,
`contracts` and `tests`. Tiers are `root`, `domain`, `service`, `package` or
`tool`. Only the repository root uses `tier: root` and `parent: null`.

`path` and `dependencies.internal` are repository-relative (`path: .` at
root). All other filesystem references are relative to the manifest directory:
`parent`, `entrypoints.file`, `submodules.path`, `submodules.manifest`,
`contracts.doc`, `tests.directory` and optional `files` (a list of file paths).
Paths must exist and stay inside the repository, including after symlink
resolution. A submodule manifest must be `structure.yml` directly inside the
listed descendant directory. Each child has exactly one caller, matching its
parent. Internal dependencies may cross branches; they are not parent links.
External dependencies are descriptive library or protocol names.

Custom fields are permitted. They are preserved by maintenance and are not
interpreted as arbitrary path references. `tests.command` is documentation,
never executed by the validator; run it from repository root unless the command
explicitly changes directory. Graph integrity cannot prove that summaries
match implementation: review responsibilities and boundaries when code changes.

## Validation

Run before concluding work or submitting a pull request:

```bash
python scripts/lint_structure.py
python -m pytest -q tests/test_structure.py
devenv tasks run context:check
```

The standalone linter uses the existing PyYAML dependency and Git; use the
repository Python environment or `uv run --locked python scripts/lint_structure.py`.
It reads `git ls-files --cached --others --exclude-standard` scoped to manifest
names, including new non-ignored manifests. It does not walk environments,
build outputs, media directories or Git internals. Canonical manifests in
otherwise ignored output directories have explicit ignore exceptions.

Validation rejects missing fields, malformed types, duplicate YAML keys,
broken references, mismatched parents, duplicate child links, unreachable
manifests and paths escaping the repository. Failure exits with status 1 and
names the offending manifest. It neither generates files nor contacts hosts.

`devenv tasks run tests:pytest` depends on `context:check`; the repository pytest
suite also validates the real manifest graph, so existing Python CI enforces
it. The always-run pre-commit hook is defined in `devenv.nix`. Devenv generates
`.pre-commit-config.yaml` as a Nix-store symlink; regenerate through Devenv,
rather than editing the generated file.
