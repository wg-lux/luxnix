# Add a Machine to Vault-Backed Hub Transfer

This runbook enrolls a new site node, written below as `<host>`, into the
`gs-02` LX-Annotate hub and bootstraps the first audited
Django superuser on the hub when one is required. It applies to the current
LuxNix `gpu_client`/`endoreg_client` inventory model. Run secret-handling
commands as `root`. Never put unseal keys, Vault tokens, AppRole Secret IDs,
private keys, node shared secrets, application master keys, or passwords in
Git, Nix, terminal arguments, logs, or chat.

This is an operator runbook. Clinical users must not perform these steps. A
machine is ready only after the configuration, key, service, identity, and
disposable-transfer checks at the end of this guide all pass.

## Identities and keys

The deployment uses independent credentials for independent purposes. Do not
substitute one for another.

| Material | Purpose | Authoritative location | May leave that location? |
| --- | --- | --- | --- |
| Vault Shamir unseal shares | Unlock Vault after a restart | Authorized custodians | Never install on `gs-02` or any site node |
| Temporary Vault operator token | Reconcile PKI, AppRole, and node secrets | Operator session on `gs-02` | No; unset immediately after use |
| Vault server CA | Authenticate `vault.endo-reg.net` | `/var/lib/luxnix-vault-pki/ca.crt` on `gs-02`; pinned copy on each site | Public certificate; deliver through an authenticated channel and verify its fingerprint separately |
| Vault AppRole Role ID and Secret ID | Authenticate one site to Vault | `/etc/secrets/vault/hub-pki/approle_role_id` and `approle_secret_id` on that site | Only in the encrypted, host-specific enrollment delivery |
| Hub-transfer client certificate and key | mTLS identity of one site | `/var/lib/lx-annotate/hub-pki/client.crt` and `client.key` on that site | Certificate may be inspected; private key must remain on that site |
| Hub-transfer client CA | Let Nginx validate site certificates | `/var/lib/lx-annotate/hub-pki/client-ca.pem` on `gs-02` | Public certificate only |
| `NetworkNode` shared secret | Application request authentication in addition to mTLS | `source-node-secret` on the site and `<host>-source-node-secret` on `gs-02` | Only through the approved encrypted enrollment channel; never use it for payload encryption |
| Hub X25519 recipient key pair | Wrap and unwrap a fresh per-transfer data-encryption key | Private key only on `gs-02`; public key delivered to sites through Vault | Only the public key may leave `gs-02` |
| LX-Annotate application master key | Encrypt local application-managed storage | Host-local secret storage on each node | Never transmit it and never reuse it as a node secret or transfer key |
| LUKS/disk unlock material | Protect the local storage boundary | Host/custodian-specific boot procedure | Never distribute as hub-transfer enrollment material |

The mTLS certificate, `NetworkNode` secret, and X25519 public recipient key are
all required. mTLS authenticates the channel, the shared secret authenticates
the application request, and envelope encryption protects the standalone
processed-media payload. The long-lived application master key is not part of
the transfer protocol.

## Prerequisites and recorded deployment evidence

Before editing or deploying, record all of the following in the approved
deployment record:

- the new hostname, FQDN, VPN address, and immutable `center_key`;
- the reviewed LuxNix repository path and `git rev-parse HEAD`;
- `flake.lock` digest and `git status --short` output;
- the target `gs-02` and site NixOS configurations;
- the selected LX-Annotate version and immutable wheel or Nix closure digest;
- the operator and Vault custodian responsible for enrollment;
- the intended Keycloak username for the hub superuser, when applicable.

Use a durable checkout outside `/tmp`. Do not deploy unrelated dirty changes.
Confirm that the site is reachable through the clinical VPN, its SSH host key
has been verified, its protected storage is mounted, and `gs-02` is the intended
central hub. The center named by `<center-key>` must already exist in both
application databases; node provisioning fails closed for an unknown center.

### Run the repository preflight

From the exact durable checkout intended for deployment, validate one explicit
site before obtaining a Vault token or creating enrollment material:

```bash
devenv shell vault-site-preflight <host>
```

Use `--json` for structured deployment evidence. The command is local and
read-only. It refuses inventory groups and fails when the checkout is dirty,
the configured deployment source differs, required inventory groups are
missing, the host's Ed25519 SSH identity is not pinned for its hostname, FQDN,
and VPN address, the temporary enrollment exception is fleet-wide, evaluated
Vault or mTLS settings differ from the approved contract, or `gs-02` lacks one
matching receiver node.

The preflight does not connect to the site, read enrollment files, confirm
protected storage, or prove that Vault is unsealed. After it reports `READY`,
run the separately cataloged connectivity check and then continue with the
trusted `gs-02` checks below:

```bash
devenv shell check-connectivity <host>
```

Do not issue credentials when either command fails. Correct the canonical YAML
or source-state problem, regenerate when necessary, and rerun the checks.

## 1. Check and unseal Vault

In this deployment, `gs-02` is configured as the central hub. On a trusted
`gs-02` session, set the local authenticated endpoint before checking state:

```bash
sudo -i
export VAULT_ADDR="https://172.16.255.22:8200"
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
vault status
```

If `Sealed` is `true`, an authorized custodian must run the following and type
the saved unseal share at the hidden prompt:

```bash
vault operator unseal
vault status
```

Continue only when Vault reports `Initialized true` and `Sealed false`. Vault
must be unsealed after every `gs-02` reboot or Vault restart. Never initialize
an existing Vault again just because it is sealed.

Obtain a short-lived, scoped administrative token through the approved Vault
owner procedure. Read it at a hidden prompt; do not paste it into a command
line or save it in a shell profile:

```bash
read -rsp "Temporary Vault enrollment token: " VAULT_TOKEN
echo
export VAULT_TOKEN
vault token lookup >/dev/null
```

## 2. Bootstrap the hub engines

Use the short-lived token without placing it in shell history:

```bash
luxnix-vault-bootstrap-hub-pki

systemctl restart luxnix-vault-publish-hub-client-ca.service
systemctl is-active vault.service \
  luxnix-vault-publish-hub-client-ca.service
```

The bootstrap is idempotent. It prepares `lx-hub-pki`, `lx-hub-secrets`, and
AppRole authentication. It also validates or creates the hub X25519 recipient
key pair and publishes only the public key to Vault. It refuses an implicit
recipient-key rotation. The client-CA publisher must become `active`.

## 3. Add the declarative YAML configuration

Add the site to `ansible/inventory/hosts.ini` and create or update
`ansible/inventory/host_vars/<host>.yml`. The site must be a member of both
`gpu_client` and `endoreg_client`; active production sites also belong in
`active_clients`. Add storage, language, SSH, or maintenance groups only when
they reflect the real host.

The current transfer defaults are owned by
`ansible/inventory/group_vars/gpu_client.yml`, not by an individual host file.
That shared YAML enables outbound transfer, mTLS, Vault AppRole, recipient-key
delivery, and the two local `NetworkNode` records. Review the shared file but
do not copy its settings into every host. The host-specific YAML must at least
declare the real center:

```yaml
host_roles:
  endoreg_client.defaultCenterKey: '"<center-key>"'
```

The shared group configuration derives the site node key and client certificate
common name from `config.networking.hostName`, and derives the owning center
from `endoreg_client.defaultCenterKey`. Override those values only for a
reviewed migration; aliases or mismatched node keys break deterministic
transfer identity.

Add the matching receiver-side node to
`ansible/inventory/host_vars/gs-02.yml` under
`luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes`:

```nix
{
  nodeKey = "<host>";
  displayName = "<host> site node";
  role = "site_node";
  centerKey = "<center-key>";
  sharedSecretFile = "/etc/secrets/vault/hub-pki/<host>-source-node-secret";
}
```

The node key and center key must exactly match the site configuration. The hub
secret path is host-qualified because `gs-02` stores one independently delivered
request-authentication secret per site. Do not put the secret value in YAML.

Initial enrollment may set the following temporary exception in the site's
`ansible/inventory/host_vars/<host>.yml` under `host_luxnix`:

```yaml
vault.client.auth.deferUntilProvisioned: "true"
```

It permits that site's NixOS switch before AppRole files arrive, but it does
not permit LX-Annotate to start without its required secrets. The value must
not be placed in `group_vars/gpu_client.yml`: enrollment state belongs to one
machine, and an unfinished site must not weaken the rest of the fleet.

Validate and regenerate derived Nix configurations:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval '.#nixosConfigurations.<host>.config.system.build.toplevel.drvPath'
nix eval '.#nixosConfigurations.gs-02.config.system.build.toplevel.drvPath'
nix build '.#nixosConfigurations.<host>.config.system.build.toplevel' --no-link
nix build '.#nixosConfigurations.gs-02.config.system.build.toplevel' --no-link
```

Review generated diffs and confirm both evaluated configurations contain the
same node key, center key, and secret-file paths. Do not hand-edit the generated
`systems/x86_64-linux/<host>/default.nix` or `gs-02/default.nix`.

The hosts entry deliberately keeps Vault resolution on the declared VPN path;
it does not weaken or replace TLS verification. Its trade-off is that a Vault
VPN-address change requires a reviewed configuration rollout. Remove it only
after an authoritative internal DNS path has been deployed and verified from
the site. Falling back accidentally to external DNS is not an availability
strategy.

## 4. Enroll the site

Back on `gs-02`, obtain a short-lived administrative token as in step 2, then:

```bash
install -d -m 0700 /root/vault-enrollment
luxnix-vault-enroll-hub-site \
  <host>.intern /root/vault-enrollment/<host>
unset VAULT_TOKEN
```

The output contains:

- `approle_role_id`
- `approle_secret_id`
- `vault-server-ca.pem`
- `vault-server-ca.sha256`
- `client-ca.pem`
- `source-node-secret`

Move this bundle only through the approved encrypted secret-delivery channel.
`vault-server-ca.pem` is the stable CA, not the renewable Vault server leaf.
Verify the fingerprint printed by the enrollment command against trusted
`gs-02` state before installing it.
The AppRole login implementation that hides credentials from process arguments
must be deployed before issuing and activating replacement Secret IDs.

Before delivering the bundle, install the receiver copy of the node secret on
`gs-02`. The source path remains in the root-only enrollment directory and the
destination name must use the exact site node key:

```bash
install -d -o root -g sensitiveServices -m 0750 /etc/secrets/vault/hub-pki
install -o root -g sensitiveServices -m 0640 \
  /root/vault-enrollment/<host>/source-node-secret \
  /etc/secrets/vault/hub-pki/<host>-source-node-secret
```

Do not copy the hub X25519 private recipient key into the enrollment bundle.
`luxnix-vault-bootstrap-hub-pki` keeps it on `gs-02` and publishes only its
public counterpart to the authenticated site's Vault policy.

## 5. Install files before switching configurations

On the site, place the decrypted enrollment directory in a root-only location,
verify the stable Vault CA against the fingerprint obtained independently from
trusted `gs-02` state, and install the delivered files:

```bash
sudo openssl x509 -in /root/vault-enrollment/<host>/vault-server-ca.pem \
  -noout -subject -issuer -fingerprint -sha256

# Compare this output with the fingerprint read independently on gs-02.
# Stop on any mismatch.
sudo install -d -o root -g root -m 0700 /etc/secrets/vault/hub-pki
sudo install -o root -g root -m 0400 \
  /root/vault-enrollment/<host>/approle_role_id \
  /etc/secrets/vault/hub-pki/approle_role_id
sudo install -o root -g root -m 0400 \
  /root/vault-enrollment/<host>/approle_secret_id \
  /etc/secrets/vault/hub-pki/approle_secret_id
sudo install -o root -g root -m 0644 \
  /root/vault-enrollment/<host>/vault-server-ca.pem \
  /etc/secrets/vault/hub-pki/vault-server-ca.pem
sudo install -o root -g sensitiveServices -m 0640 \
  /root/vault-enrollment/<host>/source-node-secret \
  /etc/secrets/vault/hub-pki/source-node-secret
```

The resulting static enrollment files have these contracts:

| Path | Owner | Mode |
| --- | --- | --- |
| `/etc/secrets/vault/hub-pki/approle_role_id` | `root:root` | `0400` |
| `/etc/secrets/vault/hub-pki/approle_secret_id` | `root:root` | `0400` |
| `/etc/secrets/vault/hub-pki/vault-server-ca.pem` | `root:root` | `0644` |
| `/etc/secrets/vault/hub-pki/source-node-secret` | `root:sensitiveServices` | `0640` |

The site and hub copies of `source-node-secret` must match. Compare a SHA-256
digest in two trusted root sessions without displaying file contents, then keep
the digest only in the restricted enrollment evidence:

```bash
# Site
sudo sha256sum /etc/secrets/vault/hub-pki/source-node-secret

# gs-02
sudo sha256sum /etc/secrets/vault/hub-pki/<host>-source-node-secret
```

After the first successful AppRole login, LuxNix creates or refreshes these
runtime files; do not manufacture them manually:

| Runtime path on the site | Source and purpose |
| --- | --- |
| `/var/lib/lx-annotate/hub-pki/client.crt` | Vault-issued mTLS client certificate |
| `/var/lib/lx-annotate/hub-pki/client.key` | Private key for that client certificate |
| `/var/lib/lx-annotate/hub-pki/client-ca.pem` | Issuing client CA returned by Vault |
| `/etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem` | Vault-authenticated hub X25519 public recipient key |

Install the static files before either host configuration references them;
otherwise the fail-closed services stop activation. `client-ca.pem` from the
enrollment output is public verification material and is not a substitute for
the independently published receiver CA or the generated site runtime files.

After confirming delivery and recording the required restricted evidence,
securely remove decrypted temporary enrollment copies from both machines. Keep
only the approved encrypted custodian backup required by the credential policy.

## 6. Deploy and verify

Deploy the reviewed `gs-02` configuration first so the receiver knows the new
node before the sender can queue work. Then deploy the reviewed site
configuration. Use the same durable repository revision that passed evaluation
and build:

```bash
# On gs-02
nh os switch . -- --accept-flake-config
systemctl restart lx-annotate-hub-node-provisioning.service

# On the site
nh os switch . -- --accept-flake-config
systemctl reset-failed vault-auth-setup.service
systemctl restart vault-auth-setup.service
```

If a site configuration was deliberately switched before its enrollment files
arrived, `vault.client.auth.deferUntilProvisioned = true` makes the missing-file
case a non-failing systemd condition, but LX-Annotate still remains fail-closed.
`luxnix-vault-enrollment-status` distinguishes `enrollment-pending`,
`tls-trust-failed`, `vault-sealed`, `vault-unreachable`, `auth-rejected`, and
`vault-error`. Never create an empty `vault.env` or weaken TLS to move past one
of those states.

After the site switch and static secret installation, start the authentication
and managed-secret chain explicitly:

```bash
sudo systemctl reset-failed \
  vault-auth-setup.service \
  managed-secrets-setup.service \
  luxnix-vault-issue-hub-client-certificate.service
sudo systemctl start vault-auth-setup.service
sudo luxnix-vault-enrollment-status
sudo systemctl start managed-secrets-setup.service
sudo systemctl start luxnix-vault-issue-hub-client-certificate.service
sudo systemctl restart lx-annotate-hub-node-provisioning.service
```

The enrollment status must be successful. Set this site's temporary
`host_luxnix.vault.client.auth.deferUntilProvisioned` value to `false`, then
regenerate, build, and switch this site again. Do not wait for another site to
finish enrollment. From that point onward, missing credentials and real Vault
authentication failures block activation for this site normally.

Verify without displaying file contents or credential values:

```bash
# Site
systemctl is-active \
  vault-auth-setup.service \
  managed-secrets-setup.service \
  luxnix-vault-issue-hub-client-certificate.service \
  lx-annotate-hub-envelope-key-preflight.service \
  lx-annotate-hub-node-provisioning.service \
  lx-annotate-celery-hub-transfer-worker.service \
  redis-lx-annotate.service \
  lx-annotate.service

# Hub
systemctl is-active \
  vault.service \
  luxnix-vault-publish-hub-client-ca.service \
  nginx.service \
  postgresql.service \
  redis-lx-annotate.service \
  lx-annotate-hub-envelope-key-preflight.service \
  lx-annotate-hub-node-provisioning.service \
  lx-annotate.service
```

Validate formats, ownership, certificate identity, and key pairing. These
commands print metadata and public-key digests, never private material:

```bash
# Site
sudo stat -c '%U:%G %a %n' \
  /etc/secrets/vault/hub-pki/approle_role_id \
  /etc/secrets/vault/hub-pki/approle_secret_id \
  /etc/secrets/vault/hub-pki/source-node-secret \
  /var/lib/lx-annotate/hub-pki/client.crt \
  /var/lib/lx-annotate/hub-pki/client.key \
  /etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem
sudo openssl verify \
  -CAfile /var/lib/lx-annotate/hub-pki/client-ca.pem \
  /var/lib/lx-annotate/hub-pki/client.crt
sudo openssl x509 -in /var/lib/lx-annotate/hub-pki/client.crt \
  -noout -subject -issuer -dates -checkhost <host>.intern
sudo openssl pkey \
  -pubin -in /etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem \
  -text_pub -noout | grep X25519

# Compare these two site outputs; they must match.
sudo openssl x509 -in /var/lib/lx-annotate/hub-pki/client.crt \
  -pubkey -noout | openssl pkey -pubin -outform DER | sha256sum
sudo openssl pkey -in /var/lib/lx-annotate/hub-pki/client.key \
  -pubout -outform DER | sha256sum

# gs-02: validate the current X25519 private key and derive its public digest.
sudo openssl pkey \
  -in /etc/secrets/vault/hub-pki/hub-recipient-current.pem \
  -text -noout | grep X25519
sudo openssl pkey \
  -in /etc/secrets/vault/hub-pki/hub-recipient-current.pem \
  -pubout -outform DER | sha256sum

# Site: this public digest must match the digest derived on gs-02.
sudo openssl pkey \
  -pubin -in /etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem \
  -outform DER | sha256sum
```

Run the packaged acceptance checks on both nodes and inspect any failed unit
before attempting a transfer:

```bash
sudo systemctl start lx-annotate-acceptance.service
systemctl --no-pager --full status lx-annotate-acceptance.service
systemctl --failed --no-pager --full
```

Finally transfer one approved, non-clinical, processed and anonymized test
artifact from the new site. Confirm all of the following:

- the sender reuses one deterministic transfer key;
- Nginx accepts the mTLS identity and does not redirect to OIDC;
- `gs-02` associates the transfer with the exact active `<host>`
  `NetworkNode` and expected center;
- envelope-key validation succeeds and no raw media is offered;
- the receiver reaches `completed`, not merely `awaiting_media`;
- the sender records the matching remote transfer ID and completion receipt;
- neither journal contains credentials, private keys, application master keys,
  patient identifiers, or raw payload data.

## 7. Bootstrap the first hub Django superuser

The Linux `admin` account, a Vault administrator, a Keycloak realm
administrator, and a Django superuser are separate identities. Do not create a
shared local Django password account for this purpose. A Django superuser is
not required for machine-to-machine transfer itself; it is required only when
an authorized person must perform global hub administration or bootstrap
otherwise incomplete local center relationships.

1. In Keycloak, grant the named personal user the exact
   `center_scope:admin` realm role plus the ordinary roles required to sign in
   to LX-Annotate. Do not treat `endoregdb_user`, `data:write`, or a similarly
   named Keycloak group as a substitute for `center_scope:admin`.
2. Have that user sign in to `https://lx-annotate.local` on `gs-02` once. This
   creates the local Django user and synchronizes the exact role into its local
   groups. A login on a study laptop does not create the hub-local record.
3. Add this temporary setting to
   `ansible/inventory/host_vars/gs-02.yml` under `host_services`:

   ```yaml
   luxnix.lxAnnotateLocal.centerAdminBootstrap.username: '"<keycloak-username>"'
   ```

4. Run Autoconf validation and generation, evaluate and build `gs-02`, review
   the diff, and switch the reviewed configuration:

   ```bash
   devenv tasks run autoconf:check
   devenv tasks run autoconf:generate
   nix eval '.#nixosConfigurations.gs-02.config.system.build.toplevel.drvPath'
   nix build '.#nixosConfigurations.gs-02.config.system.build.toplevel' --no-link
   nh os switch . -- --accept-flake-config
   ```

5. Verify the audited one-shot on `gs-02`:

   ```bash
   systemctl --no-pager --full status lx-annotate-center-admin-bootstrap.service
   journalctl -u lx-annotate-center-admin-bootstrap.service -b --no-pager
   ```

   It must report that the existing user was promoted to Django staff and
   superuser and that the immutable audit entry was persisted. A missing user,
   missing exact group, or unavailable audit ledger is a hard failure; correct
   the cause instead of creating a fallback user.

6. Remove `centerAdminBootstrap.username` from the YAML immediately after the
   successful bootstrap. Regenerate, build, and switch `gs-02` again so the
   promotion unit is no longer part of the active configuration.
7. Have the promoted user sign in again and verify the protected
   Administration workflow. Assign center relationships through that audited
   workflow. Do not edit synchronized Django groups manually.

The bootstrap command is idempotent, but removing the temporary option does not
revoke an already granted superuser. Revocation requires removal of the
Keycloak role and a separately reviewed, audited local-superuser revocation
procedure on `gs-02`.

## 8. Readiness record

Do not declare the new study laptop ready until the deployment record contains:

- reviewed LuxNix revision, locked inputs, LX-Annotate version, and artifact
  digest for both targets;
- successful Autoconf validation, evaluation, and builds;
- stable Vault server-CA fingerprint and valid server SAN evidence;
- site mTLS certificate subject, issuer, expiry, and certificate/key match;
- matching site/hub node-secret digests in restricted evidence;
- matching site/hub X25519 public-key digests;
- successful node provisioning on both databases;
- successful service and LX-Annotate acceptance checks on both nodes;
- successful disposable end-to-end transfer and receiver completion;
- successful audited hub-superuser bootstrap and removal of its temporary YAML
  option, when a new superuser was required;
- confirmation that decrypted enrollment staging was removed and no secret was
  committed, copied into `/nix/store`, or exposed in logs.

## 9. Migrate an already enrolled site to the stable server CA

Do this only after reviewing and building the durable `gs-02` configuration.
Do not obtain trust material with `curl`, `openssl s_client`, a browser, or any
other connection to the unauthenticated Vault endpoint.

On a trusted `gs-02` console or SSH session whose host key has already been
verified, read the CA and its fingerprint directly from local state:

```bash
sudo openssl x509 -in /var/lib/luxnix-vault-pki/ca.crt \
  -noout -subject -issuer -fingerprint -sha256
sudo openssl verify -CAfile /var/lib/luxnix-vault-pki/ca.crt \
  -purpose sslserver /var/lib/luxnix-vault-pki/server.crt
sudo openssl x509 -in /var/lib/luxnix-vault-pki/server.crt \
  -noout -checkhost vault.endo-reg.net
sudo openssl x509 -in /var/lib/luxnix-vault-pki/server.crt \
  -noout -checkhost gs-02.intern
sudo install -m 0644 /var/lib/luxnix-vault-pki/ca.crt \
  /root/vault-server-ca.pem
```

Transfer that file through the approved authenticated, encrypted delivery
channel. Obtain the expected fingerprint from the trusted `gs-02` console over
a separate trusted view, not from the transferred file or the network endpoint.
On the site, validate and atomically install it without restarting anything:

```bash
sudo luxnix-vault-install-server-ca \
  /root/vault-server-ca.pem \
  '<SHA-256 fingerprint copied from trusted gs-02 state>'
sudo luxnix-vault-enrollment-status || true
```

The installer rejects a fingerprint mismatch and rejects a non-CA certificate.
Only after the NixOS configuration and CA fingerprint are both reviewed, start
the chain explicitly:

```bash
sudo systemctl reset-failed vault-auth-setup.service managed-secrets-setup.service
sudo systemctl start vault-auth-setup.service
sudo luxnix-vault-enrollment-status
sudo systemctl start managed-secrets-setup.service
sudo systemctl start luxnix-vault-issue-hub-client-certificate.service
```

Leaf renewal is automatic under the unchanged CA and needs no client update.
CA replacement is deliberately not automatic: it requires this authenticated
migration again and clients with the old CA must fail closed. Never use
`VAULT_SKIP_VERIFY`, disable TLS verification, create an empty `vault.env`, or
fetch replacement trust material from the unauthenticated endpoint.

Keep application-suite failures separate from this certificate acceptance
check. In particular, an EndoReg settings bootstrap failure such as
`settings.SETTINGS_MODULE` being unset does not show whether the Vault CA,
server leaf, or client authentication works. Track and fix it independently;
the TLS evidence is certificate verification under the configured CA, SAN
validation, and the explicit Vault client state reported above.

## 10. Rotation or removal

Normal Vault TLS renewal changes only the server leaf and key while preserving
the CA. Re-enrollment creates replacement AppRole material while preserving the
per-node Vault policy. Deliver and activate the replacement atomically, then
revoke the old Secret ID/token. To remove a machine, stop its transfer worker,
revoke its AppRole and certificates, remove its KV node secret, and deactivate
its `NetworkNode`. Treat removal as a separate reviewed operation; do not delete
Vault paths or receiver records during routine enrollment.

Use these lifecycle boundaries:

| Material | Normal lifecycle |
| --- | --- |
| Vault server leaf | Renewed automatically under the stable server CA; sites need no trust change |
| Vault server CA | Manual authenticated migration using the fingerprint-pinned procedure above |
| Site mTLS certificate | Issued and renewed by `luxnix-vault-issue-hub-client-certificate.service` and its timer |
| AppRole Secret ID | Replace through a new encrypted enrollment delivery, verify the new login, then revoke the old ID |
| `NetworkNode` shared secret | Rotate only in a coordinated maintenance window with the sender stopped and both site and hub copies updated before reprovisioning |
| Hub X25519 recipient key | Explicit reviewed rotation only; publish the new public key and retain the retiring private key until every persisted or in-flight envelope using it has drained |
| Application master key | Host-local encrypted-storage procedure only; never rotate or distribute it as part of hub enrollment |

For removal, preserve transfer and audit records, disable the sender, revoke
its Vault access and mTLS identity, remove its secret delivery, and mark the
receiver-side `NetworkNode` inactive. Do not delete completed transfer evidence
or reuse the removed node key for another physical machine.
