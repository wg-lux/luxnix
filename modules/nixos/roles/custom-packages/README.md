# NixOS package ownership

`roles.custom-packages` is the canonical owner for optional, host-wide package
bundles. Shared development tools belong in `baseDevelopment`; desktop,
office, GPU, cloud, and host-specific additions belong in their corresponding
opt-in bundle. Hosts select bundles through the role options instead of
declaring the same packages in host or service modules.

`roles.common.packages` owns the small baseline required by the common NixOS
role. Development and filesystem tooling such as `e2fsprogs` belongs to the
custom bundle, even when a host also enables the common role.

Service modules may add packages only when they are hard runtime dependencies
of the service (for example, filesystem helpers required by an enabled mount).
Interactive development tools and general administration utilities remain in
`roles.custom-packages` or a user/Home Manager module.

The video-editing bundle selects standard OBS with `cudaSupport = false` to
reuse the upstream binary cache. In the pinned recipe this removes only a
redundant driver-path hook; NVENC, Wayland, PipeWire, and the existing driver
runpath fixups are preserved. Global CUDA support for other applications is
unchanged, and `programs.obs-studio.package` remains overridable. The evaluated
feature and dependency comparison in `tests/test_package_cache_contract.py`
must pass when updating nixpkgs. See the
[build diagnosis](../../../../../docs/guides/cuda-source-builds.yml) for evidence.

Host cache additions belong to `luxnix.generic-settings.nix.extraSubstituters`
and `extraTrustedPublicKeys`. They merge with NixOS's standard cache at normal
priority; `mkDefault` on the final lists would discard the extra caches. The
CUDA cache is `https://cache.nixos-cuda.org`; its retired Cachix URL is removed
from both the daemon defaults and the flake settings.

`cli.programs.nix-ld` owns the common `nix-ld` library set.
`roles.custom-packages` contributes only opt-in libraries, currently the CUDA
runtime bundle, through `cli.programs.nix-ld.extraLibraries`. Host roles should
select the relevant bundle and must not redeclare either library set.
