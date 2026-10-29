# Vault-backed hub enrollment

Use this guide to enroll configured site machines into the `gs-02` hub or to
repair an existing enrollment. The normal path is one controller command,
[`enroll-reachable-hub-sites`](#enroll-a-configured-site). The
[manual procedure](#manual-enrollment) remains for cases the command does not
cover. Clinical video approval is a separate workflow.

## What you need before starting

The **controller** is the machine where you run the command. The **site** sends
recordings; the **hub** (`gs-02`) receives them. Run from a clean, reviewed
LuxNix checkout outside `/tmp`, as the controller's normal administrator. Moving
the checkout to another controller does not move SSH authorization, sudo
permissions or Vault credentials.

| Requirement | What it means |
| --- | --- |
| Controller SSH key | The controller's administrator must already connect to every selected site and to `gs-02`, including when the controller is `gs-02` itself. See [Controller SSH authorization](#controller-ssh-authorization). Keep private keys on their owning machine. |
| Verified SSH host keys | `conf/ssh-host-keys/known_hosts` must contain verified server identities. These pins authenticate servers; they do not grant login. Never disable host-key checking to fix access. |
| Linux sudo password | The password of the SSH login account, normally `admin`, **on the named target**. Hosts can have different passwords. It is neither an SSH key nor a Vault credential. |
| Vault unseal shares | Custodian recovery material used only when Vault is sealed. Unsealing does not authenticate anyone. |
| Vault enrollment token | A short-lived token from the Vault custodian with the reviewed enrollment policy. See [Issue a short-lived enrollment token](#issue-a-short-lived-enrollment-token). An AppRole credential, unseal share or Linux password cannot replace it. |
| Deployed configuration | The site and `gs-02` already run a configuration that contains the site (see [Add a new site](#add-a-new-site-to-the-configuration)), with protected storage, `/dev/shm` as tmpfs and encrypted or disabled swap. |

Ansible calls privilege elevation **become**; here it means sudo to root.
`--ask-sudo-password` asks separately for each reachable host and is preferred.
The legacy `--ask-become-pass` asks once for one shared password. Omit both only
when the target accounts have noninteractive sudo. Never pass passwords with
`-e`, save them in inventory, or paste them into chat.

### Controller SSH authorization

The inventory group `hub_enrollment_admin_access` (`gs-02`, `gc-02`, `gc-06`,
`gc-09`, `gc-10`) supplies the `gs-02` administrator public key as
`services.ssh.authorizedKeys`. The key only works from `172.16.255.22`, with
forwarding and PTY allocation disabled; Ansible command execution still works.

The key is installed only once the target **runs** a NixOS generation that
contains it. If SSH reports `Permission denied (publickey)`, check the target's
`/etc/ssh/authorized_keys.d/admin`. When the key is missing there, the
target's active generation predates the key: switch the target to the reviewed
revision first.

For a target that cannot be switched yet, `ansible/playbooks/deploy_hub_admin_access.yml`
appends the same restricted key to `/home/admin/.ssh/authorized_keys` from a
controller that already has access. Preview first, then rerun without
`--check --diff`:

```bash
bash scripts/run-secret-playbook.sh ansible/playbooks/deploy_hub_admin_access.yml \
  -i ansible/inventory/hosts.ini --limit <host> --ask-become-pass --check --diff
```

It preserves other keys and does not restart SSH, activate NixOS or change sudo
policy. Removing this authorization later requires removing both the
declarative key and that file entry.

## Enroll a configured site

1. Check access and configuration before obtaining a Vault token. Replace
   `gc-09` consistently with the intended site:

   ```bash
   devenv shell vault-site-preflight gc-09 --controller
   devenv shell check-connectivity gc-09
   devenv shell check-connectivity gs-02
   ```

   The preflight is local and read-only. It fails when the checkout is dirty,
   the deployment source differs, inventory groups are missing, the site's
   Ed25519 SSH identity is not pinned for its hostname, FQDN and VPN address,
   Vault or mTLS settings differ from the approved contract, or `gs-02` lacks a
   matching receiver node. `--controller` validates delivery from a separate
   controller checkout; add `--json` for structured evidence. The preflight does
   not connect to the site or prove that Vault is unsealed. The connectivity
   check tests SSH and remote command execution, not sudo or Vault access.

2. Have the Vault custodian confirm that Vault is initialized and unsealed and
   hand over a short-lived enrollment token through the approved private
   channel ([custodian procedures](#vault-custodian-procedures)).

3. Run from the controller's normal administrator shell:

   ```bash
   devenv shell enroll-reachable-hub-sites --site gc-09 --ask-sudo-password
   ```

   Enter each named host's sudo password at the hidden prompts. Review the
   displayed hub address, reachable sites, revision and `flake.lock` digest,
   then enter the **Vault enrollment token**. No token prompt appears when no
   site passes the prerequisites. The wrapper ignores an inherited
   `VAULT_TOKEN`. `--help` shows the options without connecting.

4. On each enrolled site, refresh the Vault-managed secrets. The command does
   not restart `managed-secrets-setup.service`, so Vault-backed files such as the
   center identity salt or the Keycloak secret stay stale until it runs again:

   ```bash
   sudo systemctl restart managed-secrets-setup.service
   ```

5. Read the per-site results and complete the
   [verification](#verify) and [readiness record](#readiness-record).

For one run, the command bootstraps the hub engines with
`luxnix-vault-bootstrap-hub-pki` and restarts the client-CA publisher. For each
reachable site, it reconciles the site's identity against Vault, delivers the
bundle through private tmpfs, installs the recipient public key and restarts
`vault-auth-setup.service`. It then requires state `ready`, issues the client
certificate and starts its timer, validates the envelope key, reprovisions the
node on both hosts, and starts `lx-annotate.service` and the transfer worker.
Starting the worker can resume queued work. `enrolled` does not approve clinical
recordings or prove a transfer.

The command does not activate a NixOS configuration or rotate node secrets,
salts or media keys. Reconciliation reuses valid saved and installed
credentials. It creates a new bundle only for a site that has neither; it never
replaces a credential that Vault rejects.

Without `--site`, the command considers every host in `active_clients`,
`gpu_client` and `endoreg_client`. A run fails if no site enrolls or any
reachable site fails; unreachable sites are reported and can be retried. Fix the
first reported blocker and rerun the same command. Do not delete identities to
force a retry.

## Troubleshooting enrollment

| Result or message | Check and next action |
| --- | --- |
| `unreachable`, SSH connection closed or timed out, `Permission denied (publickey)` | Check the controller VPN route, login account, [authorized key](#controller-ssh-authorization) and host-key pin. `unreachable` does not prove the host is off. A sudo password or Vault token cannot repair SSH. |
| `failed-prerequisite` | Use the named target's Linux password, with `--ask-sudo-password` for differing passwords. Verify that `/dev/shm` is tmpfs. |
| `failed-connectivity` | SSH works but remote execution failed. Check the remote Python interpreter. Ansible's ping module is not an ICMP ping. |
| `failed-preflight` | Correct the reported inventory, receiver center, source-state or trust mismatch before issuing credentials. |
| `failed-enrollment` | Inspect the first failed task. Saved bundles remain for retry; re-enrollment is not breach recovery. |
| `Saved and installed credentials conflict`, `Role ID mismatch`, `Node secret mismatch` | Stop. Nothing was replaced. Resolve which identity is authoritative before retrying. |
| A rejected Secret ID (`secret-id/lookup` fails) | Reconciliation does not replace it. Prepare a fresh bundle and use [routine AppRole replacement](#routine-approle-replacement). |
| `Site is contained` | The site is under [breach containment](#breach-containment-and-replacement); fleet enrollment cannot restore it. |
| `Verify hub helper and persistent enrollment storage` fails | `/var/lib/luxnix-vault-site-lifecycle`, `/root/vault-enrollment/<site>` and `/etc/secrets/vault/hub-pki` on `gs-02` need encrypted backing storage and protected swap. Preserve existing state when migrating them; do not delete saved identities or trace the task with `no_log` disabled. |
| Vault connection refused at `127.0.0.1` | Set `VAULT_ADDR` and `VAULT_CACERT` in the shell that runs `vault`. |
| Vault sealed | Ask the custodian to unseal. Never initialize an existing Vault again. |
| Vault permission denied | Verify the token's policy and lifetime with its issuer. Do not substitute a root token. |

### Enrollment states

`sudo luxnix-vault-enrollment-status` prints `Vault enrollment state: <state>`
and exits nonzero for anything but `ready`. Never write the status file by hand
or create an empty `vault.env` to move past a state.

| State | Meaning and next action |
| --- | --- |
| `ready` | The last authentication succeeded. |
| `enrollment-pending` | Role ID, Secret ID or Vault CA file is missing or empty. Install the enrollment bundle. |
| `tls-trust-failed` | The installed CA does not authenticate the Vault server. Use the [stable server CA migration](#migrate-an-already-enrolled-site-to-the-stable-server-ca). |
| `vault-sealed` | The custodian must unseal Vault on `gs-02`. |
| `vault-unreachable` | Check the VPN route and Vault service. TLS verification stays mandatory. |
| `auth-rejected` | Vault rejected the AppRole material. Replace it through authenticated delivery. |
| `vault-error` | Unclassified failure; read `journalctl -u vault-auth-setup.service -b`. |
| `offline-cached` | No fresh authentication; services with a cached-artifact policy continue. |
| `unknown` | `vault-auth-setup.service` has not recorded a state yet. |

Every site in `gpu_client` sets `vault.client.allowOffline = true`. On those
sites a failed AppRole login is recorded as **`offline-cached`, not
`auth-rejected`**, and dependent units fail later with errors such as an empty
hub source-node secret. Read the actual cause with
`sudo journalctl -u vault-auth-setup.service -b`.

## Add a new site to the configuration

Do this once per site, before enrollment. Never put secret values in YAML.

1. Add the site to `ansible/inventory/hosts.ini` in `gpu_client`,
   `endoreg_client` and, for active production sites, `active_clients`. Add it
   to `hub_enrollment_admin_access` when `gs-02` acts as controller.
2. Declare the real center in `ansible/inventory/host_vars/<host>.yml`:

   ```yaml
   host_roles:
     endoreg_client.defaultCenterKey: '"<center-key>"'
   ```

   `ansible/inventory/group_vars/gpu_client.yml` owns the transfer defaults
   (outbound transfer, mTLS, AppRole, recipient-key delivery, `NetworkNode`
   records, `allowOffline`). Do not copy them into host files. The node key and
   certificate common name derive from the hostname, the owning center from
   `defaultCenterKey`; override them only in a reviewed migration.
3. Add the receiver node to `ansible/inventory/host_vars/gs-02.yml` under
   `luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes`. Node key and center key
   must exactly match the site:

   ```nix
   {
     nodeKey = "<host>";
     displayName = "<host> site node";
     role = "site_node";
     centerKey = "<center-key>";
     sharedSecretFile = "/etc/secrets/vault/hub-pki/<host>-source-node-secret";
   }
   ```

   The center must already exist in both application databases; node
   provisioning fails closed for an unknown center.
4. Optionally, to switch the site before its bundle arrives, set this
   temporary exception in its host file under `host_luxnix`, never in
   `group_vars/gpu_client.yml`:

   ```yaml
   vault.client.auth.deferUntilProvisioned: "true"
   ```

   The missing-file case then becomes a non-failing condition. The base
   application may run on its local secrets; certificate issuance, transfer,
   node provisioning and the envelope-key preflight stay inactive. Set it back
   to `"false"` and switch again as soon as enrollment succeeds. Never keep it
   to suppress renewal failures.
5. Validate, regenerate and build:

   ```bash
   devenv tasks run autoconf:check
   devenv tasks run autoconf:generate
   nix build '.#nixosConfigurations.<host>.config.system.build.toplevel' --no-link
   nix build '.#nixosConfigurations.gs-02.config.system.build.toplevel' --no-link
   ```

   Review the generated diff; both configurations must contain the same node
   key, center key and secret paths. Do not hand-edit generated
   `systems/x86_64-linux/*/default.nix`.
6. Deploy `gs-02` first, so the receiver knows the node before the sender can
   queue work, then the site, with the documented `rebuild-host-switch` workflow
   from the same revision.

Generated site configurations map `vault.endo-reg.net` to the Vault VPN address
through `networking.hosts`. This keeps Vault resolution on the VPN without
weakening TLS verification. A Vault VPN-address change therefore needs a
reviewed configuration rollout.

## Vault custodian procedures

### Check and unseal Vault

On a trusted `gs-02` session, first run **only** `sudo -i` and wait for the root
prompt. Then, inside that root shell:

```bash
export VAULT_ADDR="https://172.16.255.22:8200"
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
vault status
```

If `Sealed` is `true`, an authorized custodian runs `vault operator unseal` and
types a share at the hidden prompt, repeating until `vault status` shows
`Initialized true` and `Sealed false`. Vault must be unsealed after every
`gs-02` reboot or Vault restart. Never initialize an existing Vault again.

### Issue a short-lived enrollment token

The issuer needs an existing Vault token that may create tokens for the
approved enrollment policy. LuxNix does not create a human login method or
prescribe the policy name; if neither exists, the Vault owner must establish
them first. A bare `vault token create` can inherit the issuer's broad policy
and is not this procedure.

In the trusted root shell above, enter the issuer token only at the hidden
prompt. The following replaces it immediately with a non-renewable token whose
lifetime is at most 30 minutes:

```bash
ENROLLMENT_POLICY='<approved-enrollment-administration-policy>'
read -rsp "Authorized Vault token for issuing an enrollment token: " VAULT_TOKEN
echo
export VAULT_TOKEN
vault policy read "$ENROLLMENT_POLICY" >/dev/null

enrollment_token="$(vault token create \
  -field=token \
  -display-name=luxnix-hub-enrollment \
  -policy="$ENROLLMENT_POLICY" \
  -no-default-policy \
  -ttl=30m \
  -explicit-max-ttl=30m \
  -renewable=false)"
VAULT_TOKEN="$enrollment_token"
unset enrollment_token
export VAULT_TOKEN

vault token lookup -format=json | jq '.data | {policies, ttl, renewable, explicit_max_ttl}'
```

If policy lookup or creation fails, run
`unset VAULT_TOKEN enrollment_token ENROLLMENT_POLICY` and stop. The lookup must
show the approved policy, a TTL of at most 30 minutes and `renewable false`;
never print the full lookup response. Because the token excludes the default
policy, the enrollment policy must permit `auth/token/lookup-self` and
`auth/token/revoke-self`. `permission denied` on creation is an authorization
blocker, not a reason to use the root token.

Keep the token only in this shell for manual procedures, or hand it to the
controller's hidden prompt through the approved private channel. Never pass it
as an argument, save it in `~/.vault-token` or a file, paste it into chat or
enable shell tracing. When finished, revoke it:

```bash
vault token revoke -self
unset VAULT_TOKEN ENROLLMENT_POLICY
```

An expired token makes Vault commands fail closed; issue a new one through the
same procedure instead of renewing it. See HashiCorp's
[`vault token create` reference](https://developer.hashicorp.com/vault/docs/commands/token/create).

## Manual enrollment

Use these steps only when `enroll-reachable-hub-sites` cannot be used. Every
command on `gs-02` runs in the trusted root shell holding the enrollment token.

### Bootstrap the hub engines

```bash
luxnix-vault-bootstrap-hub-pki
systemctl restart luxnix-vault-publish-hub-client-ca.service
systemctl is-active vault.service luxnix-vault-publish-hub-client-ca.service
```

The bootstrap is idempotent. It prepares `lx-hub-pki`, `lx-hub-secrets` and
AppRole authentication, and validates or creates the hub X25519 recipient key
pair. It publishes only the public key and refuses an implicit key rotation.

### Create the enrollment bundle

```bash
install -d -m 0700 /root/vault-enrollment
luxnix-vault-enroll-hub-site <host>.intern /root/vault-enrollment/<host>
```

The bundle contains `approle_role_id`, `approle_secret_id`,
`vault-server-ca.pem`, `vault-server-ca.sha256`, `client-ca.pem` and
`source-node-secret`. `vault-server-ca.pem` is the stable CA, not the renewable
server leaf. The hub X25519 private key never enters the bundle.

### Deliver the bundle

From the clean, reviewed controller checkout, with the fingerprint obtained
independently from trusted `gs-02` state:

```bash
devenv shell check-connectivity gs-02
devenv shell check-connectivity <host>
devenv shell deliver-hub-enrollment --limit <host> \
  -e enrollment_expected_ca_sha256=<independently-verified-fingerprint>
```

The playbook reruns the site preflight, requires pinned SSH identities, relays
the bundle through private owner-only tmpfs, installs it with the
fingerprint-pinned site installer and installs the matching hub node secret. It
suppresses secret logs and removes staging even after failure; after an
uncatchable crash, remove any retained runtime staging yourself. It does not
start consumers. The hub directory stays for recovery and must be removed after
acceptance under the credential-retention procedure.

Without the playbook, install the receiver node secret on `gs-02`:

```bash
install -d -o root -g sensitiveServices -m 0750 /etc/secrets/vault/hub-pki
install -o root -g sensitiveServices -m 0640 \
  /root/vault-enrollment/<host>/source-node-secret \
  /etc/secrets/vault/hub-pki/<host>-source-node-secret
```

Then move the bundle to a root-only directory on the site through the approved
encrypted channel and install it:

```bash
sudo luxnix-vault-install-hub-site-enrollment \
  /root/vault-enrollment/<host> \
  '<fingerprint-obtained-independently-from-gs-02>'
```

The installer rejects symlinks, empty files, a fingerprint mismatch and a
non-CA certificate, then atomically installs:

| Path | Owner | Mode |
| --- | --- | --- |
| `/etc/secrets/vault/hub-pki/` | `root:sensitiveServices` | `0750` |
| `/etc/secrets/vault/hub-pki/approle_role_id` | `root:root` | `0400` |
| `/etc/secrets/vault/hub-pki/approle_secret_id` | `root:root` | `0400` |
| `/etc/secrets/vault/hub-pki/vault-server-ca.pem` | `root:root` | `0644` |
| `/etc/secrets/vault/hub-pki/source-node-secret` | `root:sensitiveServices` | `0640` |

After delivery, securely remove decrypted temporary copies from both machines,
keeping only the approved encrypted custodian backup.

### Start the authentication chain

On the site, after the static files are installed:

```bash
sudo systemctl reset-failed vault-auth-setup.service managed-secrets-setup.service \
  luxnix-vault-issue-hub-client-certificate.service
sudo systemctl restart vault-auth-setup.service
sudo luxnix-vault-enrollment-status        # must report: ready
sudo systemctl restart managed-secrets-setup.service
sudo systemctl start luxnix-vault-issue-hub-client-certificate.service \
  luxnix-vault-issue-hub-client-certificate.timer
sudo systemctl restart lx-annotate-hub-node-provisioning.service
```

Also restart `lx-annotate-hub-node-provisioning.service` on `gs-02`. After the
first successful login, LuxNix creates these runtime files; never create them
by hand: `/var/lib/lx-annotate/hub-pki/client.crt`, `client.key`,
`client-ca.pem`, and `/etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem`.

If the site used `deferUntilProvisioned`, set it to `"false"` now, regenerate
and switch the site again.

### Verify

These checks print metadata and public digests, never private material.

```bash
# Site
systemctl is-active vault-auth-setup.service managed-secrets-setup.service \
  luxnix-vault-issue-hub-client-certificate.service \
  lx-annotate-hub-envelope-key-preflight.service \
  lx-annotate-hub-node-provisioning.service \
  lx-annotate-celery-hub-transfer-worker.service \
  redis-lx-annotate.service lx-annotate.service

# Hub
systemctl is-active vault.service luxnix-vault-publish-hub-client-ca.service \
  nginx.service postgresql.service redis-lx-annotate.service \
  lx-annotate-hub-envelope-key-preflight.service \
  lx-annotate-hub-node-provisioning.service lx-annotate.service
```

```bash
# Site: ownership, certificate identity and key pairing
sudo stat -c '%U:%G %a %n' /etc/secrets/vault/hub-pki \
  /etc/secrets/vault/hub-pki/{approle_role_id,approle_secret_id,source-node-secret,hub-recipient-current.pub.pem} \
  /var/lib/lx-annotate/hub-pki/{client.crt,client.key}
sudo -u endoreg-service-user test -r /etc/secrets/vault/hub-pki/source-node-secret
sudo openssl verify -CAfile /var/lib/lx-annotate/hub-pki/client-ca.pem \
  /var/lib/lx-annotate/hub-pki/client.crt
sudo openssl x509 -in /var/lib/lx-annotate/hub-pki/client.crt \
  -noout -subject -issuer -dates -checkhost <host>.intern
# These two digests must match:
sudo openssl x509 -in /var/lib/lx-annotate/hub-pki/client.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER | sha256sum
sudo openssl pkey -in /var/lib/lx-annotate/hub-pki/client.key -pubout -outform DER | sha256sum
```

Two values must match between site and hub. Compare them in trusted root
sessions and keep the digests only in restricted evidence:

```bash
# Node secret: site, then gs-02
sudo sha256sum /etc/secrets/vault/hub-pki/source-node-secret
sudo sha256sum /etc/secrets/vault/hub-pki/<host>-source-node-secret

# X25519 recipient public key: gs-02 (from the private key), then site
sudo openssl pkey -in /etc/secrets/vault/hub-pki/hub-recipient-current.pem \
  -pubout -outform DER | sha256sum
sudo openssl pkey -pubin -in /etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem \
  -outform DER | sha256sum
```

Run the packaged acceptance checks on both nodes and inspect any failed unit:

```bash
sudo systemctl start lx-annotate-acceptance.service
systemctl --no-pager --full status lx-annotate-acceptance.service
systemctl --failed --no-pager --full
```

Finally transfer one approved, non-clinical, processed and anonymized test
artifact. Confirm that the sender reuses one deterministic transfer key, Nginx
accepts the mTLS identity without an OIDC redirect, `gs-02` associates the
transfer with the exact `<host>` `NetworkNode` and center, envelope-key
validation succeeds with no raw media offered, the receiver reaches `completed`
(not merely `awaiting_media`), the sender records the matching remote transfer
ID and receipt, and neither journal contains credentials, keys, patient
identifiers or payload data.

## Readiness record

Before deploying, record the hostname, FQDN, VPN address and immutable
`center_key`; the checkout path, `git rev-parse HEAD`, `flake.lock` digest and
`git status --short`; the LX-Annotate version and artifact digest; and the
responsible operator and Vault custodian.

Do not declare a site ready until the record also contains:

- successful Autoconf validation, evaluation and builds for the site and `gs-02`;
- the stable Vault server-CA fingerprint and valid server SAN evidence;
- the site certificate subject, issuer, expiry and certificate/key match;
- matching node-secret and X25519 public-key digests in restricted evidence;
- successful node provisioning, service checks and acceptance on both nodes;
- a successful disposable end-to-end transfer with receiver completion;
- the hub-superuser bootstrap and removal of its temporary option, when needed;
- confirmation that decrypted staging was removed and no secret was committed,
  copied into `/nix/store` or logged.

## Bootstrap the first hub Django superuser

The Linux `admin` account, a Vault administrator, a Keycloak realm administrator
and a Django superuser are separate identities. A Django superuser is not needed
for machine-to-machine transfer, only for global hub administration or for
bootstrapping incomplete center relationships. Do not create a shared local
Django password account.

1. In Keycloak, grant the named personal user the exact `center_scope:admin`
   realm role plus the ordinary LX-Annotate login roles. `endoregdb_user`,
   `data:write` or a similarly named group is not a substitute.
2. Have that user sign in once to `https://lx-annotate.local` on `gs-02`. This
   creates the local Django user and synchronizes the role. A login on a study
   laptop does not create the hub record.
3. Add this temporary setting to `ansible/inventory/host_vars/gs-02.yml` under
   `host_services`, regenerate, build and switch `gs-02`:

   ```yaml
   luxnix.lxAnnotateLocal.centerAdminBootstrap.username: '"<keycloak-username>"'
   ```

4. Verify the one-shot reports that the user was promoted to staff and
   superuser and that the immutable audit entry was persisted:

   ```bash
   journalctl -u lx-annotate-center-admin-bootstrap.service -b --no-pager
   ```

   A missing user, group or audit ledger is a hard failure; fix the cause
   instead of creating a fallback user.
5. Remove the option immediately, then regenerate, build and switch `gs-02`
   again.
6. Have the user sign in again and assign center relationships through the
   audited Administration workflow, never by editing synchronized groups.

Removing the option does not revoke the granted superuser. Revocation requires
removing the Keycloak role and a separately reviewed, audited revocation on
`gs-02`.

## Expired site client certificate

On the site, inspect public certificate dates and renewal state:

```bash
sudo openssl x509 -in /var/lib/lx-annotate/hub-pki/client.crt -noout -dates
sudo luxnix-vault-enrollment-status
systemctl list-timers 'luxnix-vault-issue-hub-client-certificate*' --all
```

Restore Vault availability and valid AppRole authentication first (see
[Enrollment states](#enrollment-states)). Then run the
[authentication chain](#start-the-authentication-chain) and verify the renewed
certificate and transfer-worker dependencies.

## Migrate an already enrolled site to the stable server CA

Do this only after reviewing and building the `gs-02` configuration. Never
obtain trust material with `curl`, `openssl s_client`, a browser or any other
connection to the Vault endpoint.

On a trusted `gs-02` session, read the CA and its fingerprint from local state:

```bash
sudo openssl x509 -in /var/lib/luxnix-vault-pki/ca.crt \
  -noout -subject -issuer -fingerprint -sha256
sudo openssl verify -CAfile /var/lib/luxnix-vault-pki/ca.crt \
  -purpose sslserver /var/lib/luxnix-vault-pki/server.crt
sudo openssl x509 -in /var/lib/luxnix-vault-pki/server.crt -noout -checkhost vault.endo-reg.net
sudo openssl x509 -in /var/lib/luxnix-vault-pki/server.crt -noout -checkhost gs-02.intern
sudo install -m 0644 /var/lib/luxnix-vault-pki/ca.crt /root/vault-server-ca.pem
```

Transfer the file through the approved encrypted channel. Take the expected
fingerprint from a separate trusted view of `gs-02`, not from the transferred
file. On the site:

```bash
sudo luxnix-vault-install-server-ca /root/vault-server-ca.pem \
  '<SHA-256 fingerprint copied from trusted gs-02 state>'
```

The installer rejects a fingerprint mismatch and a non-CA certificate and
restarts nothing. Then run the
[authentication chain](#start-the-authentication-chain).

Leaf renewal is automatic under the unchanged CA. CA replacement is
deliberately manual and requires this procedure again; clients with the old CA
fail closed. Never use `VAULT_SKIP_VERIFY` or disable TLS verification. An
application failure such as an unset `settings.SETTINGS_MODULE` says nothing
about Vault TLS; track it separately.

## Rotation or removal

Use the incident checklist in `secrets-management.yml` to distinguish routine
replacement from breach containment.

| Material | Normal lifecycle |
| --- | --- |
| Vault server leaf | Renewed automatically under the stable CA; sites need no change |
| Vault server CA | [Manual authenticated migration](#migrate-an-already-enrolled-site-to-the-stable-server-ca) |
| Site mTLS certificate | Issued and renewed by `luxnix-vault-issue-hub-client-certificate.service` and its timer |
| AppRole Secret ID | [Routine replacement](#routine-approle-replacement), verify the new login, then destroy the old ID |
| `NetworkNode` shared secret | Coordinated maintenance window with the sender stopped and both copies updated before reprovisioning |
| Hub X25519 recipient key | Explicit reviewed rotation only; keep the retiring private key until all envelopes using it have drained |
| Application master key | Host-local encrypted-storage procedure only; never part of hub enrollment |

AppRole Secret IDs are created with unlimited lifetime and uses
(`secret_id_ttl=0`, `secret_id_num_uses=0`). Site tokens are service tokens
with a 1-hour TTL and a 4-hour maximum. The custodian must keep a restricted
accessor inventory and explicitly
[destroy superseded Secret ID accessors](https://developer.hashicorp.com/vault/api-docs/auth/approle#destroy-approle-secret-id-accessor).
Re-enrollment alone is not breach rotation: it preserves the node secret and
does not invalidate issued tokens or certificates.

### Routine AppRole replacement

After the custodian prepares a fresh `/root/vault-enrollment/<host>` bundle on
`gs-02`, run from a clean reviewed checkout in an interactive terminal:

```bash
devenv shell rotate-hub-enrollment --limit <host> \
  -e enrollment_expected_ca_sha256='<independently-verified-CA-fingerprint>'
```

It runs preflight and connectivity checks, shows both addresses, the revision
and `flake.lock` digest, and requires typing `rotate <host>`. It then delivers
the bundle, restarts `vault-auth-setup.service`, requires `ready`, restarts
`managed-secrets-setup.service` and runs
`luxnix-vault-reissue-hub-client-certificate`. On failure it shows classified
guidance. It does not generate or revoke credentials, rotate the node secret or
release containment. After a verified test transfer, revoke the retiring Secret
ID and remove staging.

### Breach containment and replacement

Isolate the site at trusted network and receiver boundaries first; stopping a
worker on a compromised machine is not containment. Then, with an authorized
custodian token on `gs-02`:

```bash
luxnix-vault-site-lifecycle contain <host>.intern
luxnix-vault-site-lifecycle rotate <host>.intern \
  --output-directory /root/vault-enrollment/<host>
```

Containment denies the site's Vault policy, destroys its Secret IDs and revokes
matching service-token accessors. It records state under
`/var/lib/luxnix-vault-site-lifecycle`, which ordinary enrollment refuses to
undo. Rotation creates a complete new bundle with compare-and-set while the
policy stays denied; the output directory must not exist yet. On partial
failure, contain again and generate another bundle. Serialize other Vault
administration sessions. The custodian policy for this is more privileged than
enrollment; never grant it to site AppRoles. Batch tokens cannot be enumerated:
establish their absence or bounded expiry before restoring the policy.

Revoke each affected certificate serial
(`vault write lx-hub-pki/revoke serial_number=<serial>`), refresh the hub CRL and
verify that the old certificate fails at the receiver. Deliver the new bundle,
restart `lx-annotate-hub-node-provisioning.service` on both hosts and verify
that old credentials fail. Then restore that one policy:

```bash
luxnix-vault-site-lifecycle resume <host>.intern --accept-consumer-verification
luxnix-vault-reconcile-hub-sites <host>.intern
```

Restart site authentication and managed secrets, then run
`sudo luxnix-vault-reissue-hub-client-certificate` on the site; it bypasses a
still-valid cached certificate. After a reboot, rerun it while containment
remains. Verify the new identity and a test transfer before lifting network
containment. This does not revoke application sessions or rotate master keys.
Record all timestamps in the incident record.

The receiver requires an authenticated
[client CRL](https://nginx.org/en/docs/http/ngx_http_ssl_module.html#ssl_crl).
`luxnix-hub-crl-bootstrap.service` publishes a complete signed CRL set before
Nginx starts; `luxnix-hub-crl.timer` refreshes it 60 seconds after each run.
Refresh failure closes the transfer gate with HTTP 503. CRLs older than
`hub.transferApi.crlMaxAgeSeconds` (default 72 hours) or past `nextUpdate` are
rejected. List every issuer's CRL endpoint in `hub.transferApi.crlUrls` when the
client chain has several issuers. Shorten the age limit only together with the
Vault CRL expiry. TLS resumption is off and keepalive is restricted on the
transfer host, but reload does not end in-flight requests, so keep network
containment during an incident.

### Removing a site

Treat removal as a separate reviewed operation. Stop the transfer worker, revoke
the site's AppRole and certificates, remove its KV node secret and secret
delivery, and mark the receiver `NetworkNode` inactive. Keep transfer and audit
records. Never reuse the node key for another machine or delete Vault paths or
receiver records during routine enrollment.

## Shared Keycloak client secret

All sites share the confidential Keycloak client `endoregdb-api`. Keycloak
issues its secret; Vault on `gs-02` only distributes it from field
`client_secret` at `<kvMountPath>/<oidcClientSecretKvPath>`, by default
`lx-hub-secrets/oidc/endoregdb-api`. `luxnix-vault-reconcile-hub-sites` grants
every reconciled site read access and never writes the value; sites reconciled
before this grant existed need one more reconciliation.

Publish on `gs-02` with a short-lived administrative `VAULT_TOKEN`. The command
reads the secret from a hidden prompt or stdin and refuses empty values:

```bash
luxnix-vault-publish-oidc-client-secret
```

The first publication uses check-and-set `0`. Republishing the same value is a
no-op; a different value requires
`LUXNIX_VAULT_ALLOW_OIDC_CLIENT_SECRET_ROTATION=1`.

Sites opt in with `services.luxnix.lxAnnotateLocal.django.keycloakSecretViaVault`,
which requires managed secrets and enrolled hub-PKI authentication. Managed
secrets then writes `django.keycloakSecretFile` (default
`/etc/secrets/vault/keycloak.env`) as `root:root 0600` on every boot. A failed
fetch keeps the previous file and fails `managed-secrets-setup.service`.

To rotate: regenerate in Keycloak, publish with the rotation variable, then on
each site restart `managed-secrets-setup.service`,
`lx-annotate-runtime-env.service` and `lx-annotate.service`. Containing one site
requires rotating the secret for all sites.

## Transfer health failures after activation

The export health service checks the persisted export ledger, so payload
rejections can remain while Vault, certificates and node provisioning are
healthy. Read the application journal before changing credentials:

```bash
sudo journalctl --namespace=+lx-annotate -u lx-annotate-hub-export-health.service -n 30 --no-pager
```

Use the export overview to find the recording's blocker. Complete metadata,
anonymization and segment review, then wait for cleanup and export proof. For
missing frame provenance on otherwise usable media, use **Frame-Herkunft
reparieren** in Hub Export and explicitly save the unresolved mapping. This
allows an otherwise eligible transfer but disables electrical-data matching; it
does not clear cleanup failures or content mismatches. See the
[backend recovery contract](https://github.com/wg-lux/endoreg-db/blob/main/docs/video_storage_normalization.md#recover-usable-media-with-unresolved-frame-mapping).
Never invent provenance, set readiness flags in SQL, delete failed ledger
entries or bypass clinical review.

Retry the existing transfer only after the checks pass, preserving its identity
and audit history. Verify a matching receiver receipt for the current artifact,
then rerun the health service and require zero critical failures. See the
[clinical transfer guide](clinical-hub-transfer-guide.md) and the
[application export workflow](https://github.com/wg-lux/lx-annotate/blob/main/docs/guides/hub-export-workflow.md).

## Identities and keys

Each credential has one purpose. Do not substitute one for another.

| Material | Purpose | Authoritative location | May leave that location? |
| --- | --- | --- | --- |
| Vault Shamir unseal shares | Unlock Vault after a restart | Authorized custodians | Never install on `gs-02` or any site |
| Vault enrollment token | Reconcile PKI, AppRole and node secrets | Custodian session on `gs-02` | No; revoke immediately after use |
| Vault server CA | Authenticate `vault.endo-reg.net` | `/var/lib/luxnix-vault-pki/ca.crt` on `gs-02`; pinned copy on each site | Public; deliver authenticated and verify its fingerprint separately |
| AppRole Role ID and Secret ID | Authenticate one site to Vault | `/etc/secrets/vault/hub-pki/approle_*` on that site | Only in the encrypted, host-specific enrollment delivery |
| Hub-transfer client certificate and key | mTLS identity of one site | `/var/lib/lx-annotate/hub-pki/client.{crt,key}` on that site | Certificate may be inspected; the key stays on the site |
| Hub-transfer client CA | Let Nginx validate site certificates | `/var/lib/lx-annotate/hub-pki/client-ca.pem` on `gs-02` | Public |
| `NetworkNode` shared secret | Application request authentication in addition to mTLS | `source-node-secret` on the site, `<host>-source-node-secret` on `gs-02` | Only through enrollment delivery; never for payload encryption |
| Hub X25519 recipient key pair | Wrap a fresh per-transfer data key | Private key only on `gs-02`; public key delivered through Vault | Only the public key |
| LX-Annotate application master key | Encrypt local application storage | Host-local secret storage | Never transmit or reuse |
| LUKS/disk unlock material | Protect local storage | Host/custodian boot procedure | Never part of enrollment |
| Shared Keycloak client secret | LX-Annotate OIDC login | Keycloak; distributed from `lx-hub-secrets/oidc/endoregdb-api` | Only to enrolled sites through their AppRole policy |

mTLS authenticates the channel, the shared secret authenticates the
application request, and envelope encryption protects the processed-media
payload. All three are required.

## Implementation map

| File | Responsibility |
| --- | --- |
| `devenv/scripts.nix`, `devenv/commands.yml` | Expose and document the shell commands. |
| `scripts/enroll-reachable-hub-sites.sh` | Restrict options and scope, enforce pinned SSH, select the sudo prompt mode. |
| `scripts/run-secret-playbook.sh` | Confine controller secret staging to private tmpfs. |
| `ansible/playbooks/enroll_reachable_hub_sites.yml` | Discover sites, prompt for the token, bootstrap the hub, deploy and verify each site, report results. |
| `ansible/playbooks/tasks/hub_enrollment_sudo_password.yml` | Request each host's sudo password without logging it. |
| `ansible/playbooks/tasks/hub_enrollment_reconcile.yml` | Check hub storage and run reconciliation. |
| `ansible/playbooks/tasks/hub_enrollment_delivery.yml` | Reuse the fingerprint-verified installation procedure. |
| `scripts/vault/site_enrollment_preflight.py` | Validate source, evaluated configuration, receiver identities and SSH pins. |
| `scripts/vault/ensure_site_enrollment.py` | Reconcile saved and installed identities against Vault; reject conflicts. |
| `ansible/playbooks/deploy_hub_admin_access.yml` | Append the gs-02 key without replacing existing access. |
| `ansible/inventory/group_vars/hub_enrollment_admin_access.yml` | Declare the key and its source-address restriction. |
| `modules/nixos/luxnix/vault/default.nix` | Define the installed `luxnix-vault-*` commands and the enrollment state machine. |
| `tests/test_vault_fleet_enrollment.py` | Exercise reconciliation, prompts, wrapper options and failure reporting. |

## Appendix: LX-Annotate interface requirements

The application owns these changes; LuxNix supplies runtime and worker health.
Extend the existing overview and backend contracts instead of creating a second
readiness implementation.

1. Add a **Needs action** filter with counts and a per-row **Next step** button.
   Include videos without transfer jobs. Distinguish processing, anonymization
   review, segment review, cleanup, identity evidence, provenance, integrity,
   operator marking and transport readiness.
2. Return structured blocker codes and allowed actions from shared backend
   validators. `resolve_video_hub_export_state` checks approval and
   artifact/hash readiness, not every payload requirement, and a stored
   `persisted_verified` state must not imply that current payload checks pass.
   Add a guarded preflight using the sender's identity, provenance and payload
   rules, with media leases where required. Preflight must not mark, approve,
   reset or queue a video.
3. Deep-link **Review anonymization**, **Review segments**, **Check export
   readiness** and **Repair processing** to the selected video by ID, keeping
   the originating filter and a return link. Missing originals block source
   reprocessing but permit explicit unresolved-provenance acknowledgment;
   missing identity evidence requires **Request administrator recovery**.
4. Show cleanup task age, last progress, queue and worker availability, and
   whether the task is actually observed; keep "unknown" when liveness cannot be
   established. Offer a permission-checked **Inspect recovery** preview for old
   jobs that reuses the existing dispatcher and guards, never an automatic
   timeout or bulk reset.
5. Keep preflight, approval, marking and sending separate. Show the reason
   beside a disabled action, support keyboard focus, announce asynchronous
   results and keep selection after refresh. Show stages as stages; the
   percentage must not imply bytes sent. Completion requires the matching
   receiver receipt for the current artifact.

Entrypoints in LX-Annotate: `frontend/src/components/Export/HubExportOverviewComponent.vue`,
`frontend/src/stores/hubExportStore.ts`,
`frontend/src/components/VideoExamination/VideoExaminationAnnotation.vue`,
`frontend/src/components/Anonymizer/VideoBackfillRepairPanel.vue`,
`frontend/src/router/index.ts`, `lx_annotate/hub/hub_export_state.py` and
`hub_export_payloads.py`. Reuse endoreg-db's
`services/annotations/segment_validation_workflow.py` and
`services/jobs/video_post_validation_jobs.py` for cleanup semantics.

Acceptance tests should cover a stored-ready video with missing provenance, a
missing-original acknowledgment with source-reprocessing refusal, missing
identity hashes, completed cleanup without export proof, stale versus live
jobs, permission-denied actions, a video with no outbound job, deep-link
selection and keyboard navigation. Preflight must not change approvals or queue
work, and retry must preserve the transfer identity.
