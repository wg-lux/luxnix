# Network source map

Navigation map only (`derived-source-map`, schema version 1). Runtime network
data belongs to the canonical sources below; do not copy host addresses here.

## Canonical sources

| Responsibility | Repository path |
| --- | --- |
| Hosts, groups, and VPN addresses | `ansible/inventory/hosts.ini` |
| Shared OpenVPN metadata | `ansible/inventory/group_vars/all/20-network.yml` |
| Generated Nix network metadata | `ansible/inventory/group_vars/all/30-nix.yml` |
| Host overrides | `ansible/inventory/host_vars` |
| Autoconf options | `autoconf/config.yml` |
| NixOS resolution policy | `modules/nixos/luxnix/generic-settings/network/default.nix` |

## Generated consumers

- `systems/x86_64-linux/<host>/default.nix`
- `networking.hosts`

## Visualization

The entry point is `topology/default.nix`; its source is `flake.nix nixosConfigurations`.
Do not duplicate static hosts or networks in the topology module.

## Operator guides

- [Network architecture](network-architecture.md)
- [Resolution and troubleshooting](network-resolution.md)

## Invariants

- VPN addresses come from inventory ansible_host values.
- Public DNS suffixes are not emitted into shared generated hosts entries.
- Local-only aliases are emitted only for the current host.
- Service-specific pins do not replace TLS authentication.
