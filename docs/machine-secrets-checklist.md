# Machine setup secrets checklist

Use this checklist when installing or restoring a LuxNix machine, especially an
LX-Annotate site client. It identifies externally supplied credentials, locally
provisioned secrets, and optional inputs. A configured path does not prove that a
file exists or that its credential works.

Start with [Getting Started](getting-started.md). Select the exact inventory host,
reviewed revision and locked inputs, then inspect its evaluated configuration and
enabled roles. The paths below describe current defaults; host overrides and hub
roles can change the requirements. For every applicable row, record the owner,
delivery mechanism, permissions, recovery source and verification result in the
existing deployment evidence, without recording secret values.

## Credentials supplied from outside the machine

Paths in the first table are relative to `/etc/secrets/vault/`.

| File | Required by | Provisioning responsibility |
| --- | --- | --- |
| `keycloak.env` | LX-Annotate OIDC login | Supply the client secret registered with Keycloak. Managed-secrets does not generate it. |
| `SCRT_local_password_admin_password_hash` | Admin account | Deliver the validated hash through the admin-password workflow. |
| `SCRT_client_user_password_hash` | Enabled client-user account | Supply the account hash; automatic human-password generation is disabled by default. |
| `hub-pki/approle_role_id` and `hub-pki/approle_secret_id` | Vault AppRole authentication | Deliver the machine-specific enrollment credentials. |
| `hub-pki/vault-server-ca.pem` | Vault TLS and the configured outbound hub HTTPS trust | Deliver and independently verify the CA certificate. This is public trust material. |
| `hub-pki/source-node-secret` | Site node registration and outbound transfer | Supply the node credential that matches the hub's registration. |
| `hub-pki/hub-recipient-current.pub.pem` | Outbound payload encryption | Deliver the hub's authenticated public recipient key, never its private key. |

The wheel startup loader accepts a raw Keycloak client secret or an assignment
named `OIDC_RP_CLIENT_SECRET`, `KEYCLOAK_CLIENT_SECRET`, or
`DJANGO_KEYCLOAK_CLIENT_SECRET`. Other environment helpers read the entire file
as a raw value, so use a raw secret for compatibility across those consumers.
Runtime setup reads the source as root and atomically publishes a service-owned
`0600` copy in the encrypted configuration directory, alongside private signing-key
and database-password copies. The file environment variables reference those
copies; source values and permissions stay unchanged. Missing, empty or symlinked
sources stop setup. A Keycloak **server admin password** is a different credential and
cannot substitute for this file.

OpenVPN clients also require these files outside the vault directory:

| File | Purpose |
| --- | --- |
| `/etc/openvpn/ca.pem` | VPN CA certificate |
| `/etc/openvpn/crt.crt` | Machine-specific client certificate |
| `/etc/openvpn/key.key` | Matching client private key |
| `/etc/openvpn/tls.pem` | VPN TLS-auth key |

Use [Admin Passwords](admin-passwords.md), [Vault Setup](vault-setup.md),
[Access Management](access-management.md) and
[Vault Hub Machine Enrollment](vault-hub-machine-enrollment.md) for delivery.
The generic secret-copy playbook flattens filenames into the vault directory;
it is not a replacement for the enrollment workflow's nested `hub-pki` layout,
ownership and certificate checks.

## Material provisioned on the machine

On a fresh machine, verify the owning provisioner instead of manually creating
these files. During restoration, recover established encryption keys and identity
material before starting consumers; fresh random replacements cannot decrypt old
data or preserve existing identities.

| File or directory | Owner and lifecycle |
| --- | --- |
| `/etc/secrets/vault/django_secret_key` | Managed-secrets generates the local Django signing key. Preserve it or use coordinated signing rotation. |
| `/etc/secrets/vault/lx_annotate_master_key` | Local generation or Vault-backed provisioning, depending on runtime options. Local site default: `endoreg-service-user:endoreg-service`, mode `0600`. Preserve the established key with encrypted data. |
| `/etc/secrets/vault/lx_annotate_identity_active` | Identity provisioning creates or recovers the active salt; center-scoped mode instead consumes the authoritative center source. |
| `/etc/secrets/vault/lx_annotate_identity_legacy_default` | Managed compatibility material for legacy identities when enrollment is enabled. |
| `/etc/secrets/vault/lx_annotate_identity_keyring.yml` | Managed identity manifest. Preserve the referenced salts and recovery copies together. |
| `/var/lib/lx-annotate-identity-salts/` and the data directory's `.identity-salt-recovery/` | Durable identity recovery copies and receipts. |
| `/var/lib/postgresql/endoregDbLocal.password` | Local PostgreSQL application-password provisioning; external database ownership requires its own credential contract. |
| `/var/lib/lx-annotate/hub-pki/client.key`, `client.crt`, `client-ca.pem` | Vault-backed client certificate issuance after machine enrollment. |
| `/var/lib/lx-annotate-ssl/lx-annotate-selfsigned.key` and `.crt` | Local HTTPS certificate provisioning when `lxSsl` is enabled and no explicit certificate pair overrides it. |
| `/run/luxnix/vault/vault.token` and `vault.env` | Ephemeral Vault authentication outputs; do not deploy static copies. |
| `/var/lib/lx-annotate/.env.systemd` | Generated sensitive application environment; do not hand-maintain or print it. |

Managed-secrets may additionally enable `django_central_secret_key`,
`SCRT_local_password_maintenance_password`,
`SCRT_roles_system_password_keycloak_host_password`, and
`SCRT_roles_system_password_nextcloud_host_minio_credentials`. Check the evaluated
built-in secret flags and actual consumers; their presence does not imply that
the machine runs those server roles. The legacy maintenance password is not the
local application's PostgreSQL password.

## Conditional requirements

### gs-02 application storage

gs-02 uses a separate 64 GiB LUKS2 container at
`/var/lib/luxnix-app-storage.luks`, manually opened as `luxnix-app-storage`.
The ext4 filesystem mounts at `/var/lib/luxnix-app-storage`; its `application`,
`postgresql` and `wheel-conf` directories bind onto `/var/lib/lx-annotate`,
`/var/lib/postgresql` and `/var/endoreg-service-user/lx-annotate-wheel/conf`.
The application environment and PostgreSQL setup/runtime units require these
mounts and stop when they disappear. The existing identity-salt replica remains
a nested bind from the separate Vault container.

After a reboot, unlock both containers before starting consumers. Skip an
`open` command if its mapping is already open and has the expected backing file:

```bash
sudo cryptsetup open /var/lib/luxnix-vault-tls.luks luxnix-vault-pki
sudo cryptsetup open /var/lib/luxnix-app-storage.luks luxnix-app-storage
sudo systemctl start postgresql.service lx-annotate-runtime-env.service
sudo systemctl start lx-annotate.service
```

Do not repeat formatting or initial copying after migration. For initial copying,
stop application timers, paths and sockets before services, and stop PostgreSQL
and its backup jobs. Preserve ownership, modes, ACLs, extended attributes and
hard links; exclude the already-mounted `data/.identity-salt-recovery` subtree.
Verify file contents and metadata before mounting over the original paths.
Remount the salt replica above the new application bind before starting services.
Original plaintext data and filesystem snapshots remain recoverable beneath the
mounts; this migration does not erase them. Keep an independent encrypted backup
and the operator-held unlock passphrase in approved recovery custody.

On 2026-10-23, the gs-02 migration passed content and metadata comparisons,
the native NixOS switch completed, and the application, PostgreSQL and workers
started successfully. HTTPS checks against `https://gs-02.intern/` returned the
login redirect and HTTP 200 for `/static/.vite/manifest.json`. Use that certified
hostname: the current server certificate does not cover `lx-annotate.local`.
Reboot recovery and independent backup restoration still require separate tests.

### Other conditional inputs

The shared storage verifier accepts repeated, identical `SOURCE,FSTYPE` mount
reports from systemd sandbox bind mounts. Conflicting reports still fail closed,
and the backing device and swap encryption checks still apply. If identity salt
checks pass outside the service but fail inside it, inspect the mount report in
the service's mount namespace before attempting any salt recovery or replacement.

- **Local vault tooling:** `/etc/secrets/.key`, `/etc/secrets/.psk`, and the
  plaintext admin-password companion belong to the documented local vault and
  credential-management workflows. They are not Vault AppRole credentials;
  the operating-system account consumes the password hash.
- **Vault-managed application LUKS storage:** `lx_annotate_luks.key` and
  `lx_annotate_luks.uuid` under the vault directory apply only when that runtime
  mode is enabled. Follow [Encrypted Data](lx-annotate-encrypted-data.md).
  Root-disk and USB boot-unlock material have a separate lifecycle in
  [Hardware Setup](hardware-setup.md).
- **Center identity mode:** the managed source is
  `/etc/secrets/vault/lx_annotate_center_<centerKey>_identity`; the custodian must
  provision the center source in Vault and authorize the machine to read it.
  Do not replace a missing center source with a newly generated local salt.
- **External TLS, SMTP and databases:** generic paths such as `ssl_key`,
  `ssl_cert`, `smtp_user` and `smtp_pwd` only become deployment requirements when
  an enabled consumer uses them. Inspect the evaluated service options.
- **Central hubs and other services:** include the enabled server role's Vault
  custody, recipient private keys, database, backup and service credentials.
  The site-client tables are not an exhaustive server-role inventory. Follow
  [Database Ownership](database-ownership.md),
  [Vault Owner Operations](vault-owner-immediate-actions.md) and the relevant
  service runbook.

The gc-06 configuration that motivated this checklist uses local PostgreSQL,
local master-key generation, local identity-salt enrollment, self-signed HTTPS
and outbound hub transfer. Center identity mode and Vault-managed application
LUKS are disabled there. Re-evaluate these options for the selected revision;
this example is not evidence of deployed readiness.

## Setup and acceptance sequence

1. Confirm host identity and addresses using the inventory and
   [SSH Host Identity](ssh-host-identity.md). Verify the pinned host key and run
   the cataloged connectivity check before remote changes.
2. Evaluate the selected host and inspect account hash paths, enabled managed
   secrets, application secret-file options, database ownership, VPN paths and
   Vault authentication mode. Match every active consumer to a provisioner.
3. For a restore, recover durable secrets and encrypted data as one coherent
   set. For a fresh installation, prepare external credentials through the
   owning runbooks. Obtain their required operator confirmation before delivery.
4. Verify file existence, non-empty content, ownership, permissions and service
   readability without printing values. Validate key format, certificate/key
   agreement, CA trust and credential acceptance through the owning checks.
5. Follow the installed startup chain and acceptance procedure in
   [LX-Annotate Diagnostics](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/Diagnostics.md).
   Check Vault enrollment, secret provisioning, storage, database setup,
   migrations, identity/master-key gates, web service and workers. Check browser
   name resolution and TLS, OIDC login and an authorized hub-transfer acceptance
   test. A passing Nix evaluation alone does not establish any of these.
6. Record the revision and exact results in existing deployment/readiness
   evidence. Stop at the first failed gate; retain redacted diagnostics and use
   the owning recovery procedure. Do not regenerate keys, disable TLS checks or
   bypass authentication to make startup pass.

For later changes, use [Coordinated Secret Rotation](secret-rotation.md).
Rotation, enrollment and restoration are different operations; replacing every
file in the secrets directory is not a safe recovery procedure.
