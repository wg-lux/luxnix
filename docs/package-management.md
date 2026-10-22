# Installing and owning packages

The central NixOS package owner is
`modules/nixos/roles/custom-packages/default.nix`.
It defines the existing optional bundles and combines `luxnix.packages.shared`,
`luxnix.packages.roles` and `luxnix.packages.machine` into one deduplicated
`environment.systemPackages` contribution. These three lists work even when
`roles.custom-packages.enable` is false; that switch controls the existing bundles.

## Choose one owner

| Scope | Edit here | Selection |
| --- | --- | --- |
| General LuxNix fleet additions | `ansible/inventory/group_vars/all/70-packages.yml` | `group_luxnix.packages.shared` |
| Shared contributor tools | `modules/nixos/roles/custom-packages/default.nix` | Existing `baseDevelopment` bundle |
| Existing optional bundle | Same module | Enable its `custom_packages` option in inventory |
| Inventory group additions | That group's `.yml` file | `group_luxnix.packages.roles.<group>` |
| Reusable Nix role | Its module, inside its enable condition | `luxnix.packages.roles.<role>` |
| One machine | `ansible/inventory/host_vars/<host>.yml` | `host_luxnix.packages.machine` |
| Hard service runtime dependency | The service module | Service package/runtime path or `environment.systemPackages` |
| User-only application | Home inventory and Home Manager modules | `home.packages` / program options |
| Repository development shell | `devenv/packages.nix` | Shell packages, not deployed system packages |

The common role retains ownership of its small `roles.common.packages` baseline;
it contributes that list through `luxnix.packages.roles.common`. Existing bundle
names remain supported. A role contribution is a package list, not a role-enable
switch: keep it inside `mkIf cfg.enable` in Nix, or in the intended inventory group.
Use distinct group keys so membership in several groups retains all contributions.
Autoconf replaces the same YAML key according to inventory precedence; do not
repeat `packages.shared` in each group or `packages.machine` in group defaults.

## Add a package from nixpkgs

For a fleet addition, edit the existing mapping in `all/70-packages.yml`:

```yaml
group_luxnix:
  packages.shared:
    - pkgs.jq
```

For an inventory group, edit its existing `.yml` mapping:

```yaml
group_luxnix:
  packages.roles.gpu_server:
    - pkgs.nvtopPackages.full
```

For one machine, merge into its existing host mapping:

```yaml
host_luxnix:
  packages.machine:
    - pkgs.jq
```

Use a package expression such as `pkgs.jq`, not a quoted Nix string such as
`'"jq"'`. Nested attributes work too. The options accept Nix packages and reject
plain package names. Keep store paths out of inventory even though the upstream
package type accepts them. Do not create a second YAML mapping
with the same `host_luxnix` or `group_luxnix` key.

To select existing bundles instead, use the established inventory interface:

```yaml
host_roles:
  custom_packages.enable: "true"
  custom_packages.baseDevelopment: "true"
  custom_packages.office: "true"
```

Do not repeat bundle contents in a host file. The package aggregator removes
identical derivations appearing in multiple scopes; it does not resolve two
different versions exposing the same executable. Choose one package version at
its source instead of relying on installation order or ignoring collisions.

## Custom flakes and local packages

Package source ownership is separate from where a package is installed:

1. Declare an external source once in `flake.nix` under `inputs`; `flake.lock`
   records its exact revision. Use `inputs.nixpkgs.follows = "nixpkgs"` when the
   upstream flake supports sharing that input. Review a targeted lock update.
2. Expose its package once through the existing flake overlay. For example,
   LuxNix already maps `inputs.lx-annotate.packages.${system}.default` to
   `pkgs.lx-annotate`. Select that package attribute in any of the lists above;
   do not repeat its input URL, revision or output-selection expression per host.
3. Define a repository-owned derivation under `packages/<name>/default.nix`.
   Snowfall exposes these through the `pkgs.luxnix` namespace. Its source URL,
   hash and build recipe belong in that derivation, not in machine inventories.

For example, a machine that explicitly needs the LX-Annotate command-line
package can select `pkgs.lx-annotate` in `packages.machine`. This does not select
the application's deployment mode or replace its service runtime. Continue to
configure the LX-Annotate wheel/service through its own documented options.

The Nix store is the destination for built or downloaded packages, not another
package catalog. Select the derivation from the locked package set; avoid
hard-coded `/nix/store/...` paths and imperative `nix profile install` for
managed host packages. Binary caches change where a derivation is obtained,
not which package is selected. Cache policy belongs to the existing
`luxnix.generic-settings.nix` options.

## WinApps

The office bundle includes `pkgs.winapps` from the
[IMGW WinApps flake](https://gitlab.phaidra.org/imgw/winapps/-/blob/main/flake.nix),
pinned in `flake.lock`. The overlay in `overlays/winapps/` refreshes the fork's
outdated installer patch so setup uses the immutable packaged source.
It supplies `winapps` and `winapps-setup` on hosts with
both `roles.custom-packages.enable` and `roles.custom-packages.office` enabled,
including the desktop role. For another host, select `pkgs.winapps` through
the inventory package lists above.

This installs the Linux client; Windows, its applications and their licenses
must be provisioned separately. Follow the
[upstream setup guide](https://gitlab.phaidra.org/imgw/winapps/-/blob/main/README.md)
for a Windows VM or an existing RDP server. Choose the matching backend in
`~/.config/winapps/winapps.conf`, keep that file owned by the user with mode
`0600`, and keep credentials out of inventory and the Nix store. Verify the
server's RDP certificate before trusting it. Then run the packaged
`winapps-setup` as that user to register applications. No VM, container engine,
firewall rule or credentials are configured by the package bundle.

## Generate, inspect and install

After inventory edits, follow the [Autoconf workflow](autoconf.md), including an
isolated render comparison before replacing tracked output. Then run:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval --json '.#nixosConfigurations.gc-02.config.luxnix.packages.machine' --apply 'map toString'
nix eval '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'
nix build '.#nixosConfigurations.gc-02.config.system.build.toplevel' --no-link
```

Replace `gc-02` with the intended inventory host. Inspect `luxnix.packages.roles`
for role contributions, and `environment.systemPackages` for the full list,
including service and upstream NixOS additions. Nix-module-only edits do not
require Autoconf regeneration.

Building does not install or activate the configuration. Follow the reviewed
[deployment workflow](deployment-guide.md) for activation on the explicit host.
Do not install from a temporary render directory. Package-policy regression
coverage lives in `tests/test_package_selection.py`.
