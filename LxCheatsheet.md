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

Canonical:

```bash
devenv tasks run autoconf:finished
```

Alias:

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
