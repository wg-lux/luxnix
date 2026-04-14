# LuxNix Cheatsheet

## System switch

Canonical:

```bash
nh os switch
```

Alias:

```bash
nho
```

Fallback:

```bash
sudo nixos-rebuild switch --flake .#<host>
```

## Home switch

Canonical:

```bash
nh home switch
```

Alias:

```bash
nhh
```

## Garbage collection

Canonical:

```bash
nix-collect-garbage -d
sudo nix-store --gc
sudo nix-store --verify --check-contents --repair
```

Aliases:

```bash
cleanup
cleanup-roots
```

## VPN client service

```bash
sudo systemctl restart openvpn-aglnet.service
sudo systemctl status openvpn-aglnet.service
```

## Autoconf / generated configs

> **Note:** `bnsc` and other custom commands are defined inside the devenv environment.
> You must either be in an active devenv shell (`devenv shell`) or prefix with `devenv shell --`:
> ```bash
> devenv shell -- bnsc
> ```
> If the devenv shell is already active (e.g. via direnv), run commands directly.

Canonical:

```bash
devenv tasks run autoconf:finished
```

Alias (must be run inside devenv shell):

```bash
bnsc
```

## Vault helpers

```bash
devenv run vault-bootstrap -- --inventory ./autoconf/inventory.yml --export
devenv run validate-admin-passwords -- --vault-dir ~/.lxv --vault-key ~/.lxv.key --admin-passwords ansible/secrets/admin-passwords.yml
```

## Connectivity check

```bash
./scripts/check-connectivity.sh <host-or-group>
```
