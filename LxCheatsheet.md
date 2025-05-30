# New generation of LuxNix

These shortcuts (and more) are defined at:
luxnix/modules/home/cli/shells/shared/default.nix

## Shortcut
```bash
nho
```

## Fallback

```bash
nh os switch
```

## Fallback

```bash
sudo nixos-rebuild switch --flake .
```

# Deleting old nix Generations

```bash
`sudo rm /nix/var/nix/gcroots/auto/*`
```

# Changes to User Environment (Home)

## Update home generation

### Shortcut

```bash
nhh
```

### Fallback

```bash
nh home switch
```

# Nix garbage collection:

## Shortcut
```bash
cleanup
cleanup-roots
```

## Fallback

```bash
Nix-collect-garbage -d
Nix-store --gc
```

### After garbage cleaning:

```bash
Nix-store --verify --check-contents --repair
```

# VPN Client

The VPN client is defined at
luxnix/modules/nixos/roles/aglnet

## Service restart

```bash
sudo systemctl restart openvpn-aglnet.service
```

## Service status

```bash
sudo systemctl restart openvpn-aglnet.service
```

# Devenv Tasks

Devenv tasks and scripts are generally defined at 
/devenv/scripts.nix
/devenv/tasks.nix

## Database

### Initialize

```bash
devenv tasks run endoreg-db:init
```

### Migrate

```bash
devenv tasks run endoreg-db:migrate
```

### Full set up (init & migrate)

```bash
devenv tasks run initialize-environment:endoreg-db
```

## Autoconf

Autoconf populates the groups and hosts in /autoconf from the yml files in ansible/inventory for user management.

-> Builds nix system configs

### Run the AutoConf pipeline:

```bash
devenv tasks run autoconf:finished
```

### Shortcut (after direnv allow)

```bash
bnsc
```

## Automatic Documentation

### Generate automatic table of contents

```bash
devenv tasks run docs:toc-generator
```