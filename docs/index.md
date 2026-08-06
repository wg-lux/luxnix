# LuxNix Documentation

Use this as the entry point for setup and operations.

Agents and automation should start with the
[machine-readable project map](https://github.com/wg-lux/luxnix/blob/main/luxnix.yml)
and use the
[developer command catalog](https://github.com/wg-lux/luxnix/blob/main/devenv/commands.yml)
for canonical invocations and risk labels.

## Maintain these docs

Validate navigation and local links after documentation changes, then
regenerate the repository table of contents when `mkdocs.yaml` changes:

```bash
devenv tasks run docs:check
devenv tasks run docs:toc-generator
```

`TABLE_OF_CONTENTS.md` is derived from the MkDocs navigation; edit
`mkdocs.yaml` instead of editing that generated table manually.

## Contributor references

- [Inventory variable ownership](https://github.com/wg-lux/luxnix/blob/main/ansible/inventory/group_vars/README.md): precedence, namespaces, and durable host or group inputs.
- [Nix generation templates](https://github.com/wg-lux/luxnix/blob/main/conf/nix-templates/readme.md): ownership rules for generated NixOS and Home Manager entry points.
- [Inventory-based Tmux sessions](https://github.com/wg-lux/luxnix/blob/main/tmux/README.md): select groups, preview sessions, attach, and stop them.
- [Manual operations catalog](https://github.com/wg-lux/luxnix/blob/main/scripts/manual-operations.yml): preserved high-risk templates, blockers, and safer workflow guidance.

## Start here

- [Getting Started](./getting-started.md): canonical Day-0 onboarding path.
- [Development](./development.md): local development environment and contributor workflow.
- [Architecture](./architecture.md): repository layout, profile/role rules, and introspection workflow.
- [Autoconf and Local Inventory](./autoconf.md): centralized options, safe fact refresh, private reports, and configuration generation.
- [Deployment Guide](./deployment-guide.md): deployment details and host setup reference.

## Understand the architecture

- [Network Architecture](./network-architecture.md): canonical topology sources and network boundaries.
- [Network Resolution](./network-resolution.md): how inventory addresses become generated host mappings.
- [Database Ownership](./database-ownership.md): current PostgreSQL ownership and legacy-name guidance.

## Operations

- [Hardware Setup](./hardware-setup.md): installation and hardware-specific preparation.
- [Vault Setup](./vault-setup.md): secret bootstrap and lifecycle.
- [Vault Hub Machine Enrollment](./vault-hub-machine-enrollment.md): add, provision, verify, rotate, or remove a hub-transfer site node.
- [SSH Host Identity](./ssh-host-identity.md): host-key registry, rotation, and recovery workflow.
- [Access Management](./access-management.md): accounts, authentication, and access boundaries.
- [Clinical Hub Transfer Guide](./clinical-hub-transfer-guide.md): plain-language setup, daily transfer workflow, status meanings, and safe failure handling for medical personnel.

## Service engineering

- [Service Module Pattern](./deploying-services-lx-annotate-style.md): reusable pattern for Vault-backed service deployment.
- [lx-annotate Encrypted Data](./lx-annotate-encrypted-data.md): hostname-scoped Vault delivery and LUKS mount flow for lx-annotate.
- [lx-annotate Secure HLS](./lx-annotate-secure-hls.md): end-to-end encrypted video playback, deployment, hub boundary, readiness, and incident-response contract.
- [lx-annotate Cluster Readiness](./lx-annotate-cluster-readiness.md): release flow, completed decisions, and remaining production gates.
- [Configuration and Nixtest Suites](./testing-nixtests.md): evaluate every host and run focused safety or VM contracts.

## Implementation plans

- [Vault Hub Simplification Plan](./vault-hub-simplification-plan.yml): phased plan for one registry entry, one reconciliation, and one secure handoff.

## Troubleshooting

- [Common Errors](https://github.com/wg-lux/luxnix/blob/main/CommonErrors.md)
- [LuxNix Cheatsheet](https://github.com/wg-lux/luxnix/blob/main/LxCheatsheet.md)
