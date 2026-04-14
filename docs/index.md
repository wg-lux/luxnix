# LuxNix Documentation

Use this as the entry point for setup and operations.

## Start here

- [Quick Reference](../quickreference.md): scenario index — find the right doc for any task without reading everything.
- [Getting Started](./getting-started.md): canonical Day-0 onboarding path.
- [Deployment Guide](./deployment-guide.md): deployment details and host setup reference.
- [Vault Setup](./vault-setup.md): secret bootstrap and lifecycle.

## Configuration system

- [Ansible Workflow](./ansible-workflow.md): adding hosts, roles, and per-host configuration; variable hierarchy and inventory reference.
- [lx-administration](./lx-administration.md): how the autoconf pipeline reads Ansible inventory and generates `systems/*/default.nix` files.
- [NixOS System Settings](./nix-settings.md): custom `system.nix`, `system.boot`, and `system.locale` module reference.
- [Roles](../roles-documentation.md): per-role option and effect reference.
- [Systems](./systems.md): per-host configuration summary — auto-generated; re-run with `devenv tasks run docs:systems`.

## Core references

- [Hardware Setup](./hardware-setup.md)
- [Security](./security.md)
- [Service Architecture](./service-architecture.md)
- [User Management](./user-management.md)
- [Access Management](./access-management.md)

## Troubleshooting

- [Common Errors](../CommonErrors.md)
- [LuxNix Cheatsheet](../LxCheatsheet.md)
