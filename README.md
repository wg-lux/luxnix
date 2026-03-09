# LuxNix

LuxNix is a NixOS configuration framework for reproducible multi-host deployments with security-focused defaults.

## Start Here

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
├── systems/
├── homes/
├── docs/
└── scripts/
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
