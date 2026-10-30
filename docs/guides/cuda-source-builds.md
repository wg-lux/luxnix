# CUDA source builds after the NixOS 26.05 update

This record preserves the findings and verification reported for the source
revisions and dates below. Conversion to Markdown does not revalidate runtime
state or resolve recorded blockers.

**Schema version:** 1

**Scope:** roles.custom-packages CUDA libraries supplied to nix-ld

## Comparison

**Before:** 355a4df585b89d5ab431f8a3ea8eab9145bb7092

**After:** 312a82ed2e84c7f2765c82e53dc792de966151b9

### Changes

- The root nixpkgs input moved from nixos-25.11 to nixos-26.05.
- The locked root revision changed from 1cd347bf3355fce6c64ab37d3967b4a2cb4b878c to 6713828a351efa628b025a1adf7f43cbf8597513.
- The existing CUDA bundle still included cudaPackages.nccl unconditionally.
- Cache declarations were already present; the update did not remove them.

## Diagnosis

**Failed derivation:** `/nix/store/r47bx9gqlil2wb6xlj559v7yapxc4nqk-cuda12.9-nccl-2.28.7-1.drv`

**Dependency chain:** gc-02 system -> system-path -> ld-library-path -> NCCL

**Cause:** The new package set selects a different NCCL derivation. NCCL is packaged as a source build, so an unavailable substitute triggers compilation. The supplied log ends with No space left on device while writing GPU code into device_glue.o, after more than an hour compiling NCCL.

**Reproduction:** Importing the locked nixpkgs with its default CUDA settings reproduced the exact failing derivation. Host CUDA capability overrides are therefore not necessary to explain this particular cache miss.

**Cache probe date:** 2026-09-15

### Cache probe results

**`cache.nixos.org`:** HTTP 404 for the failing NCCL output narinfo

**`nix-community.cachix.org`:** HTTP 404 for the failing NCCL output narinfo

**`cuda-maintainers.cachix.org`:** HTTP 401 for both nix-cache-info and the output narinfo

**Limits:** These are current unauthenticated probes, not proof of cache availability at the time of the failed build. The supplied log does not show the builder's effective substituter configuration.

## Current configuration

The historical `roles.custom-packages.cuda` and `cudaNccl` switches described
below no longer exist. Select required native CUDA packages through
`luxnix.packages.machine` and required loader libraries through
`cli.programs.nix-ld.extraLibraries`; see [package ownership](https://github.com/wg-lux/luxnix/blob/main/docs/package-management.md).
The following mitigation and commands describe the recorded revision only.

## Historical mitigation

**Implementation:** `modules/nixos/roles/custom-packages/default.nix`

**Behavior:** roles.custom-packages.cuda retains the CUDA bundle but no longer adds system NCCL by default. Set roles.custom-packages.cudaNccl to true to add NCCL when both the custom package role and its CUDA bundle are enabled.

**Impact:** Applies to every host using this shared CUDA bundle. Native applications that rely on libnccl through nix-ld must opt in. Application environments with their own NCCL dependency must continue installing that dependency; this option does not supply or validate it. Test GPU workloads before activation.

### Canonical inventory opt in

```yaml
host_roles:
  custom-packages.cuda: 'true'
  custom-packages.cudaNccl: 'true'
```

### Opt in workflow

- Add the host_roles entries to the relevant inventory host YAML.
- Run devenv tasks run autoconf:check and the documented isolated rendering comparison.
- Run devenv tasks run autoconf:generate and review the generated diff.
- Inspect the build plan before building; NCCL may still compile from source.

**Remaining risk:** Other consumers can still require NCCL. Global cudaSupport and future nixpkgs updates can cause additional cache misses. This mitigation does not guarantee a binary-only system build or repair the CUDA cache.

## Verification

### Commands

- nix eval --offline --json '.#nixosConfigurations' --apply builtins.attrNames
- nix eval --offline --raw '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'
- devenv tasks run nix-quality:check
- uv run pytest -q tests/test_repository_architecture_contract.py tests/test_nix_quality_policy.py

### Results

- All 16 host names were discovered successfully.
- The gc-02 toplevel evaluated successfully after the change.
- The evaluated gc-02 system derivation closure contains no NCCL paths.
- The Nix quality check passed; all 36 selected Python tests passed.
- Evaluated library lists confirm only NCCL was removed; cudaNccl restores it, and cuda=false excludes it.
- The YAML guide parses and git diff --check passes.

### Blockers

- docs:check reports two existing duplicate-link failures in mkdocs.yaml and docs/index.md; 24 documentation tests pass.
- Tracker validation passes for all 11 definitions; module ownership readiness remains incomplete at 3/6.

### Not performed

- Full system build, to avoid triggering other expensive source builds.
- Activation or runtime GPU tests; no running host was changed.

## Obs cache followup

**Date:** 2026-10-07

**Host:** gc-02

**Process:** 1854853 (shell) -> nh os switch -> nix build; OBS compiled through ninja

**Locked revision:** b25309931cfda5f0b8805f462a29897eeae50168

**Previous locked revision:** 6713828a351efa628b025a1adf7f43cbf8597513

**Cause:** Updating nixpkgs changes package derivations. On this host the package set also enables CUDA globally. For OBS 32.1.2 that adds only the redundant autoAddDriverRunpath hook; the standard recipe already adds driver runpaths.

### Outputs

**Cuda:** `/nix/store/g4qd80y4w0g44zdqsm5nvjvf285bsq72-obs-studio-32.1.2`

**Standard:** `/nix/store/4ijwmam0rhp8qqp5myapzflpa7srhz7c-obs-studio-32.1.2`

### Cache nixos org probe

**Cuda:** 404

**Standard:** 200

### Changes

- Select the standard OBS package in the custom-packages role using an overridable default.
- Preserve global CUDA, NVIDIA PRIME, FFmpeg, and OBS build features.
- Replace the retired CUDA cache and key in host defaults; remove retired entries from flake settings.
- Merge extra cache URLs and keys at normal priority; mkDefault lost to NixOS standard-cache definitions on all 16 hosts.

**Cache reference:** `https://wiki.nixos.org/wiki/CUDA#Setting_up_CUDA_Binary_Cache`

**Wayland evidence:** loginctl show-session 3: Desktop=KDE, Type=wayland, State=active; kwin_wayland installed.

**Tests:** `tests/test_package_cache_contract.py`

### Limits

- Existing builds retain their already-evaluated dependency graph.
- Duplicate references to identical store paths do not cause repeated compilation.
- Other CUDA consumers and uncached releases can still require source builds.
- No activation or interactive recording test was performed by this audit.
