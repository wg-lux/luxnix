# Architecture

LuxNix already follows a Snowfall-based multi-host layout. Keep the repository centered on custom options and reusable profiles instead of adding direct imports across hosts.

## Layout Contract

| Path | Purpose | Rule |
| --- | --- | --- |
| `systems/` | NixOS host outputs and adjacent hardware files | Change generated `default.nix` files through inventory and templates. Keep deliberately hand-maintained disk, boot, or hardware files beside them. |
| `homes/` | Generated Home Manager entry points | Change user and host toggles through Home inventory, group variables, and host variables. |
| `modules/nixos/` | NixOS building blocks | Define options and behavior here. Prefer `roles.*`, `profiles.*`, `services.luxnix.*`, or `luxnix.*` options over raw host imports. |
| `modules/home/` | Home Manager building blocks | Mirror the NixOS module style for user-level configuration. |
| `modules/nixos/profiles/` | Bundles of defaults | Use profiles for repeated host shapes such as Endoreg clients, GPU clients, or central hubs. |
| `packages/` | Project packages | Put derivations here when they are not ordinary upstream packages. |
| `overlays/` | Package overrides | Keep package set changes here, not in host files. |
| `ansible/inventory/` | Host and group source data | Put shared values in `group_vars`, machine-specific values in `host_vars`, and membership in `hosts.ini`. |
| `autoconf/config.yml` | Autoconf pipeline options | Keep pipeline paths and inventory-wide parsing options centralized here. |
| `conf/nix-templates/` | Nix generation templates | Change rendering structure here instead of patching generated host output repeatedly. |
| `devenv/` | Contributor commands and packages | Keep wrappers in `scripts.nix`, tasks in `tasks.nix`, and the human/machine-readable command index in `commands.yml`. |
| `tests/` | Regression contracts | Keep feature tests near their canonical suite and record intentional relocations. |
| `docs/` | Operator and contributor guides | Add maintained guides here and include them in `mkdocs.yaml`. |

## Sources of Truth and Generated Output

For Autoconf-managed hosts, the data flow is:

```text
ansible/inventory/{hosts.ini,group_vars,host_vars}
                  + ansible/cmdb/*.json (local facts)
                  + autoconf/config.yml
                  + conf/nix-templates/
                  |
                  v
autoconf/inventory.yml and merged variables
                  |
                  v
systems/<platform>/<host>/default.nix
homes/<platform>/<user>@<host>/default.nix
```

Treat the files below `systems/` and `homes/` as derived output when their host
is managed by this pipeline. Make durable changes in the inventory variables,
templates, or centralized pipeline configuration, then run:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
```

The check command resolves and displays configuration without writing output.
See the [Autoconf pipeline guide](autoconf.md) for fact
refresh, strict/CI behavior, and the private inventory report workflow.

## Host Overrides

Autoconf-managed system entry points import
`systems/x86_64-linux/host-common.nix` for the shared admin/Ansible baseline.
The per-host file remains responsible for its hardware, disk, boot, network,
and service composition; `lx-test` is intentionally outside that baseline as
an isolated test profile.

For an Autoconf-managed host, express deliberate overrides in its inventory
input. The namespaces identify where each value is rendered:

```yaml
host_nixos:
  profiles.endoregClient.enable: "true"

host_roles:
  endoreg_client.defaultCenterKey: '"university_hospital_wuerzburg"'

host_luxnix:
  generic_settings.adminVpnIp: '"172.16.255.106"'
```

Autoconf renders these as `profiles.*`, `roles.*`, and `luxnix.*`
assignments. Direct imports from `modules/` in generated host output are a
smell: add a module option, expose it through the appropriate inventory
namespace, and regenerate.

## Roles And Profiles

Use roles for reusable behavior and profiles for bundles of role defaults.

- Add atomic behavior under `modules/nixos/services`, `modules/nixos/system`, `modules/nixos/security`, `modules/nixos/hardware`, or `modules/nixos/luxnix`.
- Add persona or deployment-shape defaults under `modules/nixos/roles`.
- Add cross-role bundles under `modules/nixos/profiles`.
- Prefer `mkDefault` inside profiles so hosts can override intentionally.
- Prefer direct assignments only in host files when the value is genuinely host-specific.

## Feature-Oriented Modules

For larger features, keep the feature directory cohesive. The `lx-annotate-local` module is the current model: options, config, runtime context, and scripts live together under one service directory. Use that pattern before spreading one feature across unrelated files.

## Packages

Common CLI tools belong in `modules/nixos/roles/custom-packages/default.nix`, usually in `baseDevelopment`. Service modules should only add packages that are hard runtime dependencies of that service. Host-only packages belong in the host's inventory input or in a deliberately manual host entry point.

The base development set intentionally includes repository inspection tools:

- `ripgrep` for code search
- `fd`, `duf`, `dust`, `dysk`, and `ncdu` for filesystem inspection
- `nix-tree` for dependency graph inspection
- `nixos-shell` for VM testing of host configs
- `nix-output-monitor` for readable Nix build output

## Introspection

Use these commands before changing broad module behavior:

```bash
nix eval ".#nixosConfigurations.<host>.config.<option-path>"
nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link
nixos-shell --flake ".#<host>"
nix repl
```

Inside `nix repl`, load the flake with `:lf .` and query values such as:

```nix
nixosConfigurations.gc-02.config.services.openssh.enable
```
