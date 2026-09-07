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

`cli.programs.nix-ld` owns the common `nix-ld` library set.
`roles.custom-packages` contributes only opt-in libraries, currently the CUDA
runtime bundle, through `cli.programs.nix-ld.extraLibraries`. Host roles should
select the relevant bundle and must not redeclare either library set.
