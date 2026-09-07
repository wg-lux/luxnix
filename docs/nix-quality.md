# Nix quality checks

Luxnix uses a ratcheted quality gate for its Nix source. Existing cleanup debt
is recorded as a ceiling, so contributors can run the checks immediately while
new regressions fail. Baselines must only stay equal or decrease.

The canonical policy is `nix-quality.yml` in the repository root. It defines the
scope, generated-file classification, commands, accepted exit codes, and current
ceilings. Dead-code, linter, and formatter debt are reported separately for
generated and canonical sources. Generated devenv helper files are excluded from
the source scope entirely. The runner never edits source files.

## Run the checks

Use the fast check while developing:

```console
devenv tasks run nix-quality:check
```

It first rejects untracked files below the Git-backed flake source roots, because
Nix omits them when copying a Git flake into the store. It then parses every Nix
file with `nix-instantiate --parse` and runs `deadnix`, `statix`, the repository
formatter (`nixfmt`), and `flake-checker` for ratcheted lockfile
freshness/ownership/support findings. This does not evaluate host configurations.
The same check runs as a pre-commit hook when flake source files, `flake.lock`,
the quality policy, or its runner are staged.

## Verify generators without evaluating NixOS

Use the dedicated generator gate after changing Autoconf templates, isolated
render publication, or the boot-decryption renderer:

```console
devenv tasks run nix-quality:generators
```

The gate runs exactly 61 pytest cases in four files: 20 Autoconf rendering
contracts, 26 Ansible-to-Nix output contracts, 11 Autoconf CLI contracts
(including the safe external `--nix-output` path), and four boot-renderer
contracts. It uses only source inspection, temporary-directory rendering,
`nixfmt`, `nix-instantiate --parse`, and `bash -n`; it never invokes `nix eval`,
`nix flake check`, host evaluation, or module evaluation. It does not modify
repository outputs.

CI runs this same 61-test selection in a separate `Generated Nix renderer
contracts` job and always uploads `nix-quality-generators-junit.xml` as the
`nix-quality-generators-junit` artifact, including on failure. In that job,
`nix develop .#default` only supplies the pinned CI tool environment; the pytest
test command itself performs no Nix evaluation.

The scheduled CI job runs the full check before host, module, input, or flake
changes are considered healthy. Run it locally only on a machine with enough
CPU and memory:

```console
devenv tasks run nix-quality:full
```

The full mode additionally runs `nix flake check --no-build`. It can take
several minutes because all exported NixOS and Home Manager configurations are
evaluated.

For automation or comparisons, request JSON directly:

```console
uv run python scripts/nix-quality.py --json
uv run python scripts/nix-quality.py --full --json
```

## Reduce a baseline

1. Fix a focused group of findings and verify their semantics.
2. Run the fast or full quality check.
3. Lower the corresponding ceiling in `nix-quality.yml` to the measured value.
4. Run the check again to prove that the new ceiling passes.

Do not raise a baseline simply to make CI green. A higher result means either a
new regression or an intentional policy change that requires review.

## Generated files

Autoconf-managed Host and Home Manager `default.nix` files are classified as
generated output. The deliberately hand-maintained `lx-test` integration host
is an explicit exception. Boot-decryption configuration files written by the
boot-stick setup modules are also generated, except for the `c-01` placeholder,
because that host has no enabled generator. The `gc-05`, `gc-06`, and `gs-02`
files are explicit pre-provisioning placeholders: they intentionally contain no
device UUID and remain manually maintained until an operator provisions a
stick. The exact ownership exceptions and canonical sources are recorded under
`scope` in `nix-quality.yml`.

Fix inventory/template inputs or the generating module and regenerate outputs;
do not perform bulk formatter or linter fixes directly on generated files. The
boot-stick setup commands also perform destructive device operations, so they
must never be run solely for formatting. Their final render step is delegated
to the pure `luxnix-render-boot-decryption-config` command. It accepts every
value explicitly, formats the result with `nixfmt`, and writes only the stated
output file; it never formats or mounts a device, creates key material, or
changes a LUKS key.

After enabling one of the boot-stick modules, an operator can inspect a
representative render outside the repository without touching a device:

```console
render_directory="$(mktemp -d)"
luxnix-render-boot-decryption-config \
  --output "$render_directory/boot-decryption-config.nix" \
  --usb-uuid 12345678-1234-1234-1234-123456789abc \
  --offset-bytes 52428800 \
  --keyfile-size 4096 \
  --luks-device cryptroot
```

Use the UUID, offset, keyfile size, and LUKS mapping names recorded for the
actual host when rendering a real configuration. The renderer requires the
output parent directory to exist and refuses malformed values.

Autoconf outputs can be inspected without overwriting repository files or
refreshing facts. The destination must be a new directory outside the
repository:

```console
render_parent="$(mktemp -d)"
python scripts/autoconf-pipeline.py --nix-output "$render_parent/render"
```

The renderer applies `nixfmt` before publication. Its isolated output can then
be checked with `nix-instantiate --parse`, `deadnix`, `statix`, and
`nixfmt --check`; none of these commands evaluate a NixOS configuration.

`nixfmt` is the sole formatting gate. Alejandra may remain installed for manual
legacy work, but its output is not mixed with the repository standard.
