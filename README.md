# LuxNix 🌐

LuxNix is a NixOS configuration framework for reproducible multi-host deployments with security-focused defaults.

## Start Here

| Goal | Entry point |
| --- | --- |
| Set up or deploy a host | [Getting Started](docs/getting-started.md) |
| Browse operator and contributor guides | [Documentation Home](docs/index.md) · [Documentation Map](TABLE_OF_CONTENTS.md) |
| Inspect paths, workflows, commands, and risks as data | [Project Map](luxnix.yml) · [Developer Command Catalog](devenv/commands.yml) |

## Quick Start

The final install command can repartition the target. Complete the
[Getting Started](docs/getting-started.md) checklist and confirm both the host
and target address before running it.

```bash
# Clone
git clone https://github.com/wg-lux/luxnix.git
cd luxnix

# Discover and validate a host configuration (read-only)
nix eval --json '.#nixosConfigurations' --apply builtins.attrNames
nix eval '.#nixosConfigurations.<host>.config.system.build.toplevel.drvPath'

# Build locally without creating a result link or activating it
nix build '.#nixosConfigurations.<host>.config.system.build.toplevel' --no-link

# Confirm remote connectivity without changing the host
devenv shell check-connectivity <host>

# Destructive remote install (replace <host> and <target-ip>)
nixos-anywhere --flake '.#<host>' nixos@<target-ip>

# Post-install switch on host
nh os switch
nh home switch
```

Agents and automation should read [`luxnix.yml`](luxnix.yml) first. It provides
the same entry points as structured data and labels commands that affect local
or remote state.

Alias notes:
- `nho` = `nh os switch`
- `nhh` = `nh home switch`

## Repository Structure

```text
luxnix/
├── flake.nix                 # Nix flake entry point
├── luxnix.yml                # machine-readable project map and workflows
├── TABLE_OF_CONTENTS.md      # generated documentation map
├── autoconf/                 # centralized pipeline options and intermediates
├── ansible/                  # inventory, variables, roles, and local facts
├── conf/                     # Nix generation templates
├── devenv/                   # contributor packages, tasks, and wrappers
├── shells/                   # Snowfall development-shell definitions
├── lx_administration/        # Python administration and Autoconf package
├── lib/                      # Snowfall helpers and repository task scripts
├── modules/                  # reusable Home Manager and NixOS modules
│   ├── home/
│   └── nixos/
├── packages/                 # project package definitions
├── overlays/                 # package-set overrides
├── systems/                  # generated or host-specific NixOS entry points
├── homes/                    # generated or user-specific home entry points
├── kubernetes/               # cluster deployment manifests
├── topology/                 # nix-topology module for flake output
├── scripts/                  # operational and maintenance tools
├── tmux/                     # inventory-driven session configuration
├── tests/                    # Python and Nix regression contracts
└── docs/                     # canonical operator and contributor guides
```

## Supported Host Types

- `gc-*`: development workstations
- `gs-*`: GPU servers
- `s-*`: base/service servers
- `c-*`: client-type hosts

## Internal Service Login (Project-Specific)

For environments using the EndoReg stack:

1. Log in to Keycloak: <https://keycloak.endo-reg.net/>
2. Complete required actions (email verification, OTP, password change).
3. Log in to Nextcloud via Keycloak: <https://cloud.endo-reg.net/login>

## License

MIT (see [LICENSE](LICENSE)).
