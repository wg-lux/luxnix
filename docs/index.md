# LuxNix Documentation

Choose a guide by the task you want to complete. New contributors can start
with Development; operators installing a machine should use Getting Started.
Clinical staff should use the Central Hub Transfer guide under Operations.

These Markdown guides can be read in the repository browser or from a local
checkout. Use the same branch or commit as the configuration you are working
on; instructions on another revision may describe different behavior.

Agents and automation should start with the
[machine-readable project map](https://github.com/wg-lux/luxnix/blob/main/luxnix.yml)
and use the
[developer command catalog](https://github.com/wg-lux/luxnix/blob/main/devenv/commands.yml)
for canonical invocations and risk labels.

## Contributor references

- [Documentation Compose example](docker-compose.md): preserved preview configuration and its limitations.

- [Maintaining documentation](./documentation.md): writing standards, accessibility, checks, and a first-time reader walkthrough.
- [Inventory variable ownership](https://github.com/wg-lux/luxnix/blob/main/ansible/inventory/group_vars/README.md): precedence, namespaces, and durable host or group inputs.
- [Nix generation templates](https://github.com/wg-lux/luxnix/blob/main/conf/nix-templates/readme.md): ownership rules for generated NixOS and Home Manager entry points.
- [Inventory-based Tmux sessions](https://github.com/wg-lux/luxnix/blob/main/tmux/README.md): select groups, preview sessions, attach, and stop them.
- [Manual operations catalog](https://github.com/wg-lux/luxnix/blob/main/scripts/manual-operations.yml): preserved high-risk templates, blockers, and safer workflow guidance.

## Start here

- [Getting Started](./getting-started.md): first installation, prerequisites, and preflight checks.
- [Development](./development.md): local development environment and contributor workflow.
- [Nix Quality](./nix-quality.md): formatting, lint, generator, and flake-quality checks.
- [Architecture](./architecture.md): repository layout, profile/role rules, and introspection workflow.
- [Autoconf and Local Inventory](./autoconf.md): centralized options, safe fact refresh, private reports, and configuration generation.
- [Deployment Guide](./deployment-guide.md): deployment details and host setup reference.

## Understand the architecture

- [Network source map](network-topology.md): canonical inputs and generated consumers.

- [Network Architecture](./network-architecture.md): canonical topology sources and network boundaries.
- [Network Resolution](./network-resolution.md): how inventory addresses become generated host mappings.
- [Database Ownership](./database-ownership.md): current PostgreSQL ownership and legacy-name guidance.
- [System Feature Tracking](./system-feature-tracking.md): immutable feature specifications, assessment state, migration, and recovery.

## Operations

- [Activation failure recovery](activation-failure-recovery.md): NVIDIA driver and Vault certificate failures.
- [External storage detection](external-storage-detection.md): discovery, enrollment boundaries, and diagnostic states.
- [Hub-export consumer walkthrough](lx-annotate-hub-export-mtls-consumer-walkthrough.md): roles, enrollment steps, and acceptance checks.

- [Hardware Setup](./hardware-setup.md): installation and hardware-specific preparation.
- [Virtualization](./virtualization-guide.md): virtual-machine setup and host prerequisites.
- [Vault Setup](./vault-setup.md): secret bootstrap, storage and key migration, and lifecycle.
- [HashiCorp Vault Maintainer Notes](./vault-maintainer-operations.md): restart recovery, credential failures, key loss, and escalation boundaries.
- [HashiCorp Vault Owner Operations](./vault-owner-immediate-actions.md): encrypted custody, status, seal, unseal, and recovery boundaries.
- [Admin Password Creation and Rotation](./admin-passwords.md): canonical admin credential lifecycle.
- [Coordinated Secret Rotation](./secret-rotation.md): central catalog and ordered gates across all three repositories.
- [Vault Hub Machine Enrollment](./vault-hub-machine-enrollment.md): add, provision, verify, rotate, or remove a hub-transfer site node.
- [Vault Server Rebuild](./vault-server-rebuild.md): guarded recovery after irrecoverable loss of the `gs-02` unseal share.
- [SSH Host Identity](./ssh-host-identity.md): host-key registry, rotation, and recovery workflow.
- [Access Management](./access-management.md): accounts, authentication, and access boundaries.
- [Clinical Hub Transfer Guide](./clinical-hub-transfer-guide.md): plain-language setup, daily transfer workflow, status meanings, and safe failure handling for medical personnel.

## Service engineering

- [Wheel startup](guides/lx-annotate-wheel-startup.md): dependency admission and catalogue reconciliation.
- [Operational monitoring](guides/lx-annotate-monitoring.md): timing, readiness, and rollout.
- [HLS backfill dispatch](hls-backfill-dispatch.md): dispatch order and acceptance limitations.
- [LLM configuration](guides/llm-configuration.md): shared runtime options and worker behavior.
- [LLM status](guides/llm-status.md): API readiness and sampled availability.
- [gc-02 reporting LLM](guides/gc-02-reporting-llm.md): model selection and consumer checks.

- [LX Terminology package host](./guides/lx-terminology.md): public ZIP distribution, editor publication, runtime imports, and deployment prerequisites.
- [Service Module Pattern](./deploying-services-lx-annotate-style.md): reusable pattern for Vault-backed service deployment.
- [lx-annotate Encrypted Data](./lx-annotate-encrypted-data.md): hostname-scoped Vault delivery and LUKS mount flow for lx-annotate.
- [lx-annotate Secure HLS](./lx-annotate-secure-hls.md): end-to-end encrypted video playback, deployment, hub boundary, readiness, and incident-response contract.
- [lx-annotate Cluster Readiness](./lx-annotate-cluster-readiness.md): release flow, completed decisions, and remaining production gates.
- [gs-02 Local Redis Broker Recovery](./operations/gs-02-local-redis-broker.md): preflight, activation, acceptance, rollback, and encrypted-persistence follow-up for the implemented but undeployed broker change.
- [Configuration and Nixtest Suites](./testing-nixtests.md): evaluate every host and run focused safety or VM contracts.

## Implementation plans

- Feature-tracking plans are maintained outside the published documentation set. For the
  deployed feature-state model and recovery procedure, use
  [System Feature Tracking](./system-feature-tracking.md#migration-and-recovery).

## Validate, rollback, and recovery

For documentation-only changes, run `devenv tasks run docs:check`; if
`mkdocs.yaml` navigation changed, also run
`devenv tasks run docs:toc-generator` and review the generated diff. For
configuration changes, use the preflight commands in Getting Started
before activation. If a NixOS switch is unhealthy, select a prior generation
from the boot menu or run `sudo nixos-rebuild rollback` on the affected host,
then validate with `systemctl --failed` and the relevant service checks. Keep
deployment and acceptance logs; recover feature-tracking projections by
retaining the events tree and following the Migration and recovery section in
System Feature Tracking.

## Troubleshooting

- [gc-02 memory protection](guides/gc-02-memory-protection.md): pressure policy and recorded follow-up.
- [CUDA source-build diagnosis](guides/cuda-source-builds.md): cache findings and opt-in behavior.
- [Configuration ownership audit](guides/lx-annotate-configuration-ownership-audit.md): source findings and attributed runtime evidence.
- [Clinical readiness review](guides/clinical-readiness-review.md): recorded findings, blockers, and verification limits.

- [Common Errors](https://github.com/wg-lux/luxnix/blob/main/CommonErrors.md)
- [LuxNix Cheatsheet](https://github.com/wg-lux/luxnix/blob/main/LxCheatsheet.md)
