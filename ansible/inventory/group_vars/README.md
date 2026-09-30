# Group variable ownership

Use one `<group>.yml` file for ordinary groups. The global `all` group is larger
and is split into numbered files under `all/`; both Ansible and Autoconf load
them in filename order.

| File | Responsibility |
| --- | --- |
| `all/10-vault.yml` | Vault paths and secret filenames |
| `all/20-network.yml` | Ansible and OpenVPN network inputs |
| `all/30-nix.yml` | Shared generated NixOS options |
| `all/40-repositories.yml` | Repository locations and branches |
| `all/50-ansible.yml` | Remote connection defaults |
| `all/60-authentication.yml` | Public administrator keys |

Do not create both `<group>.yml` and `<group>/`; Autoconf rejects that ambiguous
ownership. Host-specific values belong under `../host_vars/` instead.
