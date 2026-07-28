# Architecture

LuxNix already follows a Snowfall-based multi-host layout. Keep the repository centered on custom options and reusable profiles instead of adding direct imports across hosts.

## Layout Contract

| Path | Purpose | Rule |
| --- | --- | --- |
| `systems/` | Host entry points | Keep host-specific facts here: disks, boot unlock, host addresses, and deliberate overrides. |
| `homes/` | Home Manager entry points | Keep user and host-specific home toggles here. |
| `modules/nixos/` | NixOS building blocks | Define options and behavior here. Prefer `roles.*`, `profiles.*`, `services.luxnix.*`, or `luxnix.*` options over raw host imports. |
| `modules/home/` | Home Manager building blocks | Mirror the NixOS module style for user-level configuration. |
| `modules/nixos/profiles/` | Bundles of defaults | Use profiles for repeated host shapes such as Endoreg clients, GPU clients, or central hubs. |
| `packages/` | Project packages | Put derivations here when they are not ordinary upstream packages. |
| `overlays/` | Package overrides | Keep package set changes here, not in host files. |

## Host Files

Host files should be thin. A good host file enables existing options and sets values that are only true for that machine:

```nix
{
  profiles.endoregClient.enable = true;
  endoreg-client.defaultCenterKey = "university_hospital_wuerzburg";
  luxnix.generic-settings.adminVpnIp = "172.16.255.106";
}
```

Direct imports from `modules/` in a host file are a smell. Add a module option instead, then toggle that option from the host.

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

Common CLI tools belong in `modules/nixos/roles/custom-packages/default.nix`, usually in `baseDevelopment`. Service modules should only add packages that are hard runtime dependencies of that service. Host files should only add packages for one-off host needs.

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
