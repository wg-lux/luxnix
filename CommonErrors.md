# Common Errors

Start with the [project map](luxnix.yml) for canonical paths and the
[command catalog](devenv/commands.yml) for command risk and confirmation
metadata. Generated NixOS and Home Manager files are diagnostic outputs; fix
their inventory sources and regenerate them instead of editing them directly.

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

- `systems/x86_64-linux/<host>/default.nix` for the generated result only
- `ansible/inventory/hosts.ini`
- `ansible/inventory/group_vars/README.md` for shared-value ownership
- `ansible/inventory/host_vars/<host>.yml` for host-specific values

Validate the inputs, then regenerate configs:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
```

## `nhh` fails with “No home defined”

Cause:

- No matching home configuration exists for `<user>@<host>`.

Fix:

- Add the host to `ansible/inventory/home-hosts.yml`.
- Add its values to `ansible/inventory/host_vars/home/<host>.yml`.
- Keep both host sets aligned; Autoconf rejects missing and orphaned entries.
- Do not add a fake remote host or NixOS system entry for a Home-only host.

Regenerate and validate the requested user:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval ".#homeConfigurations.\"<user>@<host>\".activationPackage.drvPath"
```

## `run-ansible` or `sync-secrets` refuses to run

Cause:

- The command omitted `--limit`, supplied an empty limit, or supplied an option
  where the limit value should be.

Fix:

```bash
devenv shell run-ansible --check --diff --limit <host-or-group>
devenv shell sync-secrets --limit <host-or-group>
```

Use `--limit all` only when a full-inventory operation is deliberate and
authorized. The wrappers return Exit 2 locally before invoking Ansible when the
limit is missing or empty.

## Connectivity/deploy steps fail before build

Cause:

- SSH or inventory mismatch.

Fix:

```bash
devenv shell check-connectivity <host>
```

Then run preflight build:

```bash
nix build ".#nixosConfigurations.<host>.config.system.build.toplevel" --no-link
```

## Cleaning old generations

Inspect the roots that currently keep store paths alive:

```bash
nix-store --gc --print-roots
sudo nix-store --gc --print-roots
```

Then remove generations older than a deliberate retention period:

```bash
nix-collect-garbage --delete-older-than 30d
sudo nix-collect-garbage --delete-older-than 30d
```

Do not delete files below `/nix/var/nix/gcroots` directly. Removing roots can
make still-needed paths collectible. `nix-collect-garbage -d` is the aggressive
alternative and removes rollback generations; use it only when that loss is
intentional.
