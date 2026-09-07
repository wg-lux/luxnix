# Network Architecture

LuxNix keeps network inputs declarative and derives host resolution from the
same inventory used by Autoconf. This page explains ownership and data flow;
it does not duplicate the current host/address table.

For exact name-resolution behavior and troubleshooting, use
[Network Resolution](./network-resolution.md). Agents can inspect the compact
[network source map](./network-topology.yaml).

## Source ownership

| Information | Canonical source |
| --- | --- |
| Managed hosts, groups, and VPN addresses | `ansible/inventory/hosts.ini` |
| OpenVPN metadata not derived from inventory | `ansible/inventory/group_vars/all/20-network.yml` |
| Shared aliases, clusters, and service-host mappings | `ansible/inventory/group_vars/all/30-nix.yml` |
| Host-specific network overrides | `ansible/inventory/host_vars` |
| Autoconf path and subnet options | `autoconf/config.yml` |
| Generated `/etc/hosts` policy | `modules/nixos/luxnix/generic-settings/network/default.nix` |
| Public and local-only name policy | `docs/network-resolution.md` |

Generated files below `systems/x86_64-linux/` consume these inputs but are not
the place to maintain the shared topology.

## Data flow

```text
ansible/inventory/hosts.ini
  + group_vars and host_vars
  -> Autoconf validation and generation
  -> luxnix.generic-settings.network.hosts
  -> networking.hosts on each NixOS host
```

Autoconf derives each host's `ip-vpn` from its inventory `ansible_host` value.
The group and host variables add metadata that cannot be inferred from the
inventory, such as internal aliases, local addresses, and network clusters.

## Flake topology visualization

The `topology` flake output passes the exported `nixosConfigurations` into
`nix-topology`. Its local module, `topology/default.nix`, intentionally contains
no static hosts or networks. Add durable network data to inventory-backed NixOS
configuration rather than maintaining a second diagram-only topology.

## VPN overlay

The `aglnet` roles own the OpenVPN overlay:

- `roles.aglnet.host` provides the VPN host role.
- `roles.aglnet.client` provides the client role.
- Inventory groups decide which machines receive those roles.

The current service host is selected declaratively in the inventory. Do not
copy a host address into documentation or a second topology file; inspect the
inventory instead.

## Resolution boundaries

The network module chooses a local address only when both hosts share an
explicit network cluster and that local address exists. Otherwise it uses the
VPN address.

Two additional rules prevent ambiguous or unsafe aliases:

- public suffixes such as `.endo-reg.net` remain DNS-owned and are excluded
  from generated `/etc/hosts` entries;
- aliases listed in `localOnlyDomains`, such as `lx-annotate.local`, are emitted
  only for the current host.

A reviewed service-specific override may intentionally pin a public hostname
to a private or loopback address. Keep such exceptions next to the service or
host that requires them and continue to authenticate TLS independently.

## Change and verification workflow

1. Change `ansible/inventory/hosts.ini` for host membership or VPN addresses.
2. Change group or host variables for aliases, clusters, and service metadata.
3. Validate and regenerate:

   ```bash
   devenv tasks run autoconf:check
   devenv tasks run autoconf:generate
   ```

4. Evaluate the affected host before deployment:

   ```bash
   nix eval ".#nixosConfigurations.<host>.config.networking.hosts" --json
   ```

5. After an authorized deployment, compare NSS and DNS results as described in
   [Network Resolution](./network-resolution.md#verification).

Optional services such as monitoring or reverse proxies have their own module
options. Their presence in `modules/nixos/services/` does not mean they are
enabled on every host; inspect the selected host configuration before relying
on an endpoint.
