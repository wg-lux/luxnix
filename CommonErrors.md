# Common Errors

## `nho` / `nh os switch` permission denied

Cause:
- You are not running with required privileges.

Fix:

```bash
sudo nh os switch
# fallback
sudo nixos-rebuild switch --flake .#<host>
```

## Host missing expected packages or services

Cause:
- Roles/group assignments are incorrect.

Check:
- `systems/x86_64-linux/<host>/default.nix`
- `ansible/inventory/hosts.ini`
- `ansible/inventory/group_vars/`

Then regenerate configs:

```bash
devenv tasks run autoconf:finished
```

## `nhh` fails with “No home defined”

Cause:
- No matching home configuration exists for `<user>@<host>`.

Fix:
- Add `homes/x86_64-linux/admin@<host>/default.nix`
- Ensure matching host exists under `systems/x86_64-linux/<host>/`

Validate:

```bash
nix eval ".#homeConfigurations.\"admin@<host>\".activationPackage.drvPath"
```

## Connectivity/deploy steps fail before build

Cause:
- SSH or inventory mismatch.

Fix:

```bash
./scripts/check-connectivity.sh <host>
```

Then run preflight build:

```bash
nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link
```

## Cleaning old generations

Use canonical commands:

```bash
nix-collect-garbage -d
sudo rm /nix/var/nix/gcroots/auto/*
```

If cleanup issues persist, inspect current gcroots before deleting additional paths.
