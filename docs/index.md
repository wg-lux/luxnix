# LuxNix Documentation

Use this as the entry point for setup and operations.

## Start here

- [Getting Started](./getting-started.md): canonical Day-0 onboarding path.
- [Architecture](./architecture.md): repository layout, profile/role rules, and introspection workflow.
- [Deployment Guide](./deployment-guide.md): deployment details and host setup reference.
- [Vault Setup](./vault-setup.md): secret bootstrap and lifecycle.
- [SSH Host Identity](./ssh-host-identity.md): host-key registry, rotation, and recovery workflow.
- [lx-annotate Encrypted Data](./lx-annotate-encrypted-data.md): hostname-scoped Vault delivery and LUKS mount flow for lx-annotate.
- [lx-annotate Secure HLS](./lx-annotate-secure-hls.md): end-to-end encrypted video playback, deployment, hub boundary, readiness, and incident-response contract.
- [Deploying Services `lx-annotate`-Style](./deploying-services-lx-annotate-style.md): reusable pattern for Vault-backed service deployment using `vault-auth-setup`, `managed-secrets`, and a service-owned runtime gate.
- [Nixtest Safety Suite](./testing-nixtests.md): how to run the LuxNix safety and reachability regression tests.

## Core references

- [Hardware Setup](./hardware-setup.md)
- [Security](./security.md)
- [Service Architecture](./service-architecture.md)
- [User Management](./user-management.md)
- [Access Management](./access-management.md)

## Troubleshooting

- [Common Errors](../CommonErrors.md)
- [LuxNix Cheatsheet](../LxCheatsheet.md)
