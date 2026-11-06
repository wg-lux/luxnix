# Inventory-based Tmux sessions

LuxNix creates multi-host Tmux sessions from the canonical Ansible inventory.
Host addresses stay in `ansible/inventory/hosts.ini`; the `tmux_hosts` group
selects the default windows. Session names and startup commands live in
`tmux/config.yml`.

Use the cataloged Devenv commands from the repository root:

```console
devenv shell ssh-all
devenv shell init-server-ssh
```

Both commands accept `--group <inventory-group>` to select another inventory
group. Inspect the planned Tmux commands without creating sessions or opening
SSH connections:

```console
devenv shell ssh-all --dry-run
devenv shell init-server-ssh --group active_clients --dry-run
```

Attach to or stop the monitoring session explicitly with:

```console
devenv shell conn-server-ssh
devenv shell kill-server-ssh
```
