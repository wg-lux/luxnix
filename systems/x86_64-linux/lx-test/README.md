# lx-test

Dedicated, non-production lx-annotate integration host.

The host is hardware-neutral and can be installed as a VM or on a dedicated
server. It deliberately runs in standalone mode with local PostgreSQL and
Redis, and does not enable GPU workers or hub transfers.

Before putting it on a network, provide a host-specific disk configuration and
create isolated test credentials/data. For a production-like deployment,
enable the lx-annotate managed encrypted-data options and provision the
hostname-scoped Vault path `secret/data/nodes/lx-test/lx-annotate`.

Evaluate or deploy it with:

```bash
nix build .#nixosConfigurations.lx-test.config.system.build.toplevel
sudo nixos-rebuild switch --flake .#lx-test
sudo systemctl start lx-annotate-acceptance
```
