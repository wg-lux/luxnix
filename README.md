# LuxNix 🌐

LuxNix is a NixOS configuration framework for reproducible multi-host deployments with security-focused defaults.

## Start Here

| Goal | Entry point |
| --- | --- |
| Set up or deploy a host | [Getting Started](docs/getting-started.md) |
| Browse operator and contributor guides | [Documentation Home](docs/index.md) · [Documentation Map](TABLE_OF_CONTENTS.md) |
| Inspect paths, workflows, commands, and risks as data | [Project Map](luxnix.yml) · [Developer Command Catalog](devenv/commands.yml) |

## Inspect the repository

To read the guides, open [Documentation Home](docs/index.md) in your Git
browser or local Markdown viewer. Running LuxNix requires Nix with flakes
enabled; contributor tasks also require Devenv.

```bash
git clone https://github.com/wg-lux/luxnix.git
cd luxnix

# List the host configurations exported by this checkout
nix eval --json '.#nixosConfigurations' --apply builtins.attrNames
```

Success prints a JSON list of host names. To evaluate or build one of them,
follow [Getting Started](docs/getting-started.md). Evaluation checks whether a
configuration can be resolved; building prepares its software locally;
activation applies it to a running machine.

Validate before activation with the evaluation, build, and connectivity
checks in that guide. Installation can repartition the target, so complete its
checklist before deploying. If an activated generation is unhealthy, boot a
previous NixOS generation or run `sudo nixos-rebuild rollback` on the host,
then check `systemctl --failed` and the affected service. Keep deployment logs;
do not delete paths directly from `/nix/store`.

Contributors should start with [Development](docs/development.md) and
[Nix Quality](docs/nix-quality.md). Change generated host and home outputs
through their inventory or template inputs. For documentation changes, follow
[Maintaining documentation](docs/documentation.md).

Agents and automation should read [`luxnix.yml`](luxnix.yml) first for
structured paths, ownership, workflows, and command risks.

## Repository Structure

```text
luxnix/
├── flake.nix                 # Nix flake entry point
├── luxnix.yml                # machine-readable project map and workflows
├── secrets-management.yml    # central cross-repository rotation catalog
├── nix-quality.yml           # Nix quality policy, baselines, and progress
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
