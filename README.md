# LuxNix

LuxNix is a NixOS configuration framework for reproducible multi-host deployments with security-focused defaults.

## Start Here

- [Quick Reference](quickreference.md) — scenario index: find the right doc for any task
- [Getting Started (Day-0 canonical flow)](docs/getting-started.md)
- [Deployment Guide](docs/deployment-guide.md)
- [Vault Setup](docs/vault-setup.md)
- [Hardware Setup](docs/hardware-setup.md)
- [Common Errors](CommonErrors.md)
- [Cheatsheet](LxCheatsheet.md)

## Quick Start

```bash
# Clone
git clone https://github.com/wg-lux/luxnix.git
cd luxnix

# Validate selected host config (replace <host>)
nix eval ".#nixosConfigurations.<host>.config.system.build.toplevel.drvPath"
nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link

# Deploy (replace <host> and <ip>)
nixos-anywhere --flake ".#<host>" nixos@<ip>

# Post-install switch on host
nh os switch
nh home switch
```

Alias notes:
- `nho` = `nh os switch`
- `nhh` = `nh home switch`

## Repository Structure

```text
luxnix/
├── flake.nix
├── modules/
│   ├── home/
│   └── nixos/
│       ├── roles/          # opt-in NixOS role modules
│       └── system/         # nix, boot, locale settings
├── systems/                # generated per-host NixOS configs (do not edit by hand)
├── homes/                  # generated per-user home-manager configs
├── ansible/
│   └── inventory/
│       ├── hosts.ini       # host list and group memberships
│       ├── group_vars/     # group-level role/service/luxnix settings
│       └── host_vars/      # host-specific overrides
├── conf/
│   └── nix-templates/      # Jinja2 templates for config generation
├── autoconf/               # pipeline output (merged vars, generated inventory)
├── lx_administration/      # Python autoconf pipeline package
├── scripts/                # autoconf-pipeline.py, vault, deploy scripts
└── docs/
```

The `systems/` and `homes/` directory trees are **fully generated** by the autoconf pipeline from the Ansible inventory. See [docs/lx-administration.md](docs/lx-administration.md) and [docs/ansible-workflow.md](docs/ansible-workflow.md) for the workflow.

## Configuration workflow

All host configuration lives in `ansible/inventory/`. To change a host's NixOS options:

1. Edit the relevant `group_vars/<group>.yml` or `host_vars/<hostname>.yml`.
2. Run `devenv tasks run autoconf:finished` to regenerate `systems/<host>/default.nix`.
3. Deploy: `nh os switch` on the target host.

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
