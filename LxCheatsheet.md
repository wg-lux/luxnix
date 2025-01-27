# New generation of LuxNix

These shortcuts (and more) are defined at:
luxnix/modules/home/cli/shells/shared/default.nix

## Shortcut
nho

## Fallback

nh os switch

## Fallback
sudo nixos-rebuild switch --flake .

# Deleting old nix Generations

`sudo rm /nix/var/nix/gcroots/auto/*`

# Changes to User Environment (Home)

## Update home generation

### Shortcut

nhh

### Fallback

nh home switch

# Nix garbage collection:

## Shortcut

cleanup
cleanup-roots

Nix-collect-garbage -d
Nix-store --gc

### After garbage cleaning:
Nix-store --verify --check-contents --repair

# VPN Client

The VPN client is defined at
luxnix/modules/nixos/roles/aglnet

## Service restart

sudo systemctl restart openvpn-aglnet.service

## Service status

sudo systemctl restart openvpn-aglnet.service

# Devenv Tasks

Devenv tasks and scripts are generally defined at 
/devenv/scripts.nix
/devenv/tasks.nix

## Database

### Initialize

devenv tasks run endoreg-db:init

### Migrate

devenv tasks run endoreg-db:migrate

### Full set up (init & migrate)

devenv tasks run initialize-environment:endoreg-db


## Autoconf

Autoconf populates the groups and hosts in /autoconf from the yml files in ansible/inventory for user management.

-> Builds nix system configs

### Run the AutoConf pipeline:

devenv tasks run autoconf:finished

### Shortcut (after direnv allow)

bnsc

## Automatic Documentation

### Generate automatic table of contents

devenv tasks run docs:toc-generator
