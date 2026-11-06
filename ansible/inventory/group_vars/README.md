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
| `all/70-packages.yml` | Fleet-wide optional package additions |

Do not create both `<group>.yml` and `<group>/`; Autoconf rejects that ambiguous
ownership. Host-specific values belong under `../host_vars/` instead.
Host files should omit values already inherited from their groups. Keep an equal
host override only when it intentionally pins policy independently of its group,
and document that reason beside the override.

Home Manager groups are selected in `../home-hosts.yml`. The opt-in
`group_home_git_maddonix` group owns that user's Git name, email and allowed signer;
it is not a fleet default. Other identities remain in their home host variables.

`intel_gpu_laptop.yml` centralizes the matching hardware inputs for `gc-04`
through `gc-10`, selected explicitly in `../hosts.ini`. Differing kernel/initrd
modules and filesystems remain host overrides; Vault enrollment stays host-owned.
The consolidation preserves every host's effective settings. Hardware snapshots
in `tests/test_repository_architecture_contract.py` guard the original values;
review complete hardware differences before updating those snapshots.
