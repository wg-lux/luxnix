# Nix generation templates

These Jinja templates generate the host-specific NixOS and Home Manager
configurations. Generated files are derived outputs: edit the inventory inputs
or templates, then regenerate them instead of editing outputs by hand.

The complete operator workflow is documented in [Autoconf](../../docs/autoconf.md).

## Ownership and paths

| Kind | Canonical path |
| --- | --- |
| Pipeline options | `autoconf/config.yml` |
| System inventory | `ansible/inventory/hosts.ini` |
| Shared variables | `ansible/inventory/group_vars/` |
| Host variables | `ansible/inventory/host_vars/<host>.yml` |
| Home inventory | `ansible/inventory/home-hosts.yml` |
| Home variables | `ansible/inventory/host_vars/home/<host>.yml` |
| System template | `conf/nix-templates/systems/x86_64-linux/main/default.nix.j2` |
| Home template | `conf/nix-templates/homes/x86_64-linux/default.nix.j2` |
| Generated system | `systems/x86_64-linux/<host>/default.nix` |
| Generated home | `homes/x86_64-linux/<user>@<host>/default.nix` |

Shared variables are split into numbered files by responsibility. See
`ansible/inventory/group_vars/README.md` for the load order and ownership of
each file.

Autoconf derives `generic-settings.network.hosts.<host>.ip-vpn` from each
remotely managed host's address in `hosts.ini`. Home hosts and inherited home
groups belong in `home-hosts.yml`; system-specific and home-specific values
belong in their respective host variable files above.

## System option namespaces

- `group_roles`, `role_roles`, and `host_roles` populate `roles`.
- `group_services`, `role_services`, and `host_services` populate `services`.
- `group_luxnix`, `role_luxnix`, and `host_luxnix` populate `luxnix`.
- `group_nixos`, `role_nixos`, and `host_nixos` populate top-level NixOS
  options such as `boot.*`, `networking.*`, `hardware.*`, `nix.*`,
  `programs.*`, `systemd.*`, and `users.*`.
- `group_imports`, `role_imports`, and `host_imports` append raw Nix import
  expressions to `imports`.

Keep `roles.*`, `services.*`, and `luxnix.*` in their dedicated namespaces to
avoid duplicate top-level attribute sets in generated files.

```yaml
host_imports:
  - ./hardware-extra.nix
host_nixos:
  networking.firewall.allowedTCPPorts:
    - 22
    - 443
  boot.kernel.sysctl."net.core.rmem_max": "16777216"
```

Native YAML booleans, numbers, lists, and mappings render as Nix values.
Strings that are already Nix expressions, such as `pkgs.linuxPackages_6_6` or
`lib.mkForce "/home/admin/luxnix"`, are preserved as raw expressions. Use raw
expressions only for trusted inventory values because they become executable
Nix syntax.

## Regenerate and validate

Validate the resolved options without writing generated files:

```console
devenv tasks run autoconf:check
```

Generate all derived configurations with one of these equivalent entry points:

```console
devenv tasks run autoconf:generate
python scripts/autoconf-pipeline.py
devenv shell bnsc
```

Inside the development shell, the short `bnsc` alias is sufficient.
