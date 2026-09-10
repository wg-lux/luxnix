# LuxNix Cheatsheet

Use the [command catalog](devenv/commands.yml) for every Devenv wrapper and
task, including risk and confirmation metadata. Use the machine-readable
[project map](luxnix.yml) for repository paths and deployment workflows.

Run repository commands from the LuxNix root unless a section explicitly says
that it is a host-local command.

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

Inspect roots first:

```bash
nix-store --gc --print-roots
# alias
inspect-gcroots
```

Keep recent rollback generations:

```bash
nix-collect-garbage --delete-older-than 30d
sudo nix-collect-garbage --delete-older-than 30d
```

Aggressive cleanup removes old rollback generations:

```bash
nix-collect-garbage -d
# alias
cleanup
```

## Nix store verification and repair

Verify before attempting repair:

```bash
nix-store --verify --check-contents
```

Only after a reported integrity failure, repair the affected store through Nix:

```bash
sudo nix-store --verify --check-contents --repair
```

## VPN client service

```bash
sudo systemctl restart openvpn-aglnet.service
sudo systemctl status openvpn-aglnet.service
```

## Autoconf / generated configs

Validate centralized options without writing generated files:

```bash
devenv tasks run autoconf:check
```

Generate configurations after validation:

```bash
devenv tasks run autoconf:generate
```

Alias:

```bash
devenv shell bnsc
```

## Vault helpers

```bash
devenv shell vault-bootstrap \
  --inventory ./autoconf/inventory.yml \
  --export

devenv shell validate-admin-passwords \
  --vault-dir ~/.lxv \
  --vault-key ~/.lxv.key \
  --admin-passwords ansible/secrets/admin-passwords.yml
```

## Connectivity check

```bash
devenv shell check-connectivity <host-or-group>
```

## Ansible changes

Preview the main playbook against one explicit host or group:

```bash
devenv shell run-ansible --check --diff --limit <host-or-group>
```

After reviewing the preview, remove `--check` to apply the authorized change.
Deploy secrets separately and only with explicit authorization:

```bash
devenv shell sync-secrets --limit <host-or-group>
```

Both mutating wrappers reject an omitted or empty `--limit`. Use `--limit all`
only for a deliberate full-inventory operation.
