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
| `keycloak.env` | LX-Annotate OIDC login | Supply the client secret registered with Keycloak, or set `django.keycloakSecretViaVault` to fetch the shared secret from Vault on `gs-02` (see [shared Keycloak client secret](vault-hub-machine-enrollment.md#shared-keycloak-client-secret)). |
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

For `gc-09` and `gc-10`, the `operator_unlocked_secrets` inventory group uses
`/var/lib/luxnix-secrets.luks`, manually opened as `luxnix-secrets`, for Vault
credentials, identity-salt recovery copies and wheel configuration. The group
disables disk swap and automatic GPT swap discovery while retaining RAM-only
zram. It configures the reusable `luxnix.storage.operatorUnlocked` module,
including the separate `luxnix-app-storage` mapping and
application/PostgreSQL binds; gc-10 retains its second-disk dependency and
separate client-PKI bind. See [Manually Unlocked Site Storage](operator-unlocked-storage.md)
for the complete mount contract and activation/reboot procedure. Declaring these
mounts does not create containers or migrate existing data.

Before activating this group, format and unlock the newly prepared container,
create its filesystem, and copy and verify all four configured directories with
consumers stopped. Never activate empty bind-mount sources or rerun `luksFormat`
on an initialized container. Preserve original directories until recovery is
verified. On subsequent boots, unlock with:

```bash
sudo cryptsetup open /var/lib/luxnix-secrets.luks luxnix-secrets
```

Unlock the application container as well before starting application services.
Then start the configured mounts and authentication/secret services. Enrollment
must pass the storage guard before credentials are delivered. The enrollment
wrapper explicitly sets both `ANSIBLE_REMOTE_TEMP` and `ansible_remote_tmp` to
`/dev/shm`, so the verifier checks the staging location actually used by Ansible.

On 2026-10-23, all four directories on gc-09 and gc-10 were copied to their
unlocked containers and verified with rsync content checksums and metadata
comparison before bind mounting. Originals remain beneath the mounts. Disk swap
was stopped; only zram remained active. The storage verifier and Vault
authentication passed on both hosts. gc-10's web service initially restarted,
then a later runtime check blocked it until the application/PostgreSQL migration
described below completed.
gc-09's application and PostgreSQL directories were subsequently copied with the
database stopped into an 8 GiB `/var/lib/luxnix-app-storage.luks` container and
verified before mounting. Its nested identity-salt replica remains on the separate
secrets volume. PostgreSQL, the web service and checked workers started, client
certificate renewal succeeded, and the local application returned HTTP 301.
The `postgres` database reported a collation-version mismatch; no collation
metadata was changed as part of storage migration.

The interim live deployment uses five mount units and four service guard drop-ins
under `/etc/systemd/system.control`, plus disk-swap masks there. This avoids a full
NixOS switch while application storage is unresolved. These overrides take
precedence over generated units: reconcile them with the inventory configuration
when completing the full deployment. gc-09 also has application/PostgreSQL mount
units and guards in that directory. Reboot recovery has not yet been tested.
On gc-09, unlock both volumes before starting the application:

```bash
sudo cryptsetup open /var/lib/luxnix-secrets.luks luxnix-secrets
sudo cryptsetup open /var/lib/luxnix-app-storage.luks luxnix-app-storage
sudo systemctl start postgresql.service vault-auth-setup.service
sudo systemctl start managed-secrets-setup.service lx-annotate.service
```

These are unlock commands only; never repeat `luksFormat` on either populated
container. The mount dependencies attach the preserved salt replica after the
application directory. Retained plaintext originals remain subject to the
documented secret-retirement procedure; migration alone does not erase them.

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

On 2026-10-23, gc-10 client certificate issuance failed because
`/var/lib/lx-annotate/hub-pki` remained on unencrypted root storage. Its contents
were copied with metadata preserved and checksum-verified into
`/var/lib/luxnix-secrets/hub-client-pki`, then bind mounted at the original path.
The underlying originals were retained. Certificate issuance then succeeded.
The gc-10 inventory defines this mount and required-mount guards for issuance,
the web service and the hub-transfer worker. Matching interim units and guards
are installed under `/etc/systemd/system.control`. This does not complete
application/PostgreSQL encryption or fleet enrollment by itself. The subsequent
application-storage migration below resolved the runtime storage failure.

For gc-10's application migration, the separate 760 GiB LUKS container is
`/data/raid01/luxnix-app-storage.luks`, on its second disk. The application
and PostgreSQL bind mounts use `/var/lib/luxnix-app-storage`; the certificate
and identity-salt replica mounts remain on `luxnix-secrets` and must be
attached after the application mount. After a reboot, unlock both containers:

```bash
sudo cryptsetup open /var/lib/luxnix-secrets.luks luxnix-secrets
sudo cryptsetup open /data/raid01/luxnix-app-storage.luks luxnix-app-storage
sudo systemctl start postgresql.service vault-auth-setup.service
sudo systemctl start managed-secrets-setup.service lx-annotate.service
```

The second-disk filesystem must be mounted before opening the application
container. Formatting commands are deliberately omitted: both containers are
already initialized. Do not delete the original application/database directories
or override mount guards to regain disk space.

The gc-10 recovery operator completed checksum-verified application/PostgreSQL
cutover on 2026-10-23. Independent read-only checks on gc-09 and gc-10 confirmed
the encrypted mount sources, storage-verifier success, Vault readiness, matching
CA-verified client certificates and keys, PostgreSQL `SELECT 1`, running web and
transfer workers, and validated HTTPS 302/200 for the login redirect/frontend
manifest. The live setup still uses interim units; native activation of the
reusable module and reboot recovery remain untested. See
[Manually Unlocked Site Storage](operator-unlocked-storage.md) for deployment
gates and the existing collation-version warning.
