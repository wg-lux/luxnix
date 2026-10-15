# Vault-backed hub enrollment

Use this guide to enroll configured site machines into the `gs-02` hub or repair
an existing enrollment. Run the controller command as the normal administrator
from a clean, reviewed LuxNix checkout outside `/tmp`. The command requests root
privileges on the targets itself. Clinical video approval is a separate workflow.

## What you need before starting

The **controller** is the machine where you run the command. The **site** sends
recordings; the **hub** receives them. Moving the checkout to another controller
does not move SSH authorization, sudo permissions or Vault credentials.

| Requirement | What it means and where it is used |
| --- | --- |
| Controller SSH key | The controller's administrator must already connect to every selected site and `gs-02`, including when the controller is `gs-02` itself. Each target must authorize that public key. Keep private keys on their owning machine. |
| Verified SSH host keys | `conf/ssh-host-keys/known_hosts` must contain verified server identities. These pins authenticate servers; they do not grant administrator login. Never disable host-key checking to fix access. |
| Linux sudo password | The password of the SSH login account, normally `admin`, **on the named target**. It permits running commands as root. Hosts can have different passwords. It is neither an SSH key nor a Vault credential. |
| Vault unseal shares | Custodian recovery material used only when Vault is sealed. Unsealing makes the existing Vault available; it does not authenticate an enrollment operator. |
| Vault enrollment token | A short-lived token supplied by the Vault owner with reviewed enrollment permissions. Enter it at the hidden prompt after host checks. A site AppRole credential, unseal share or Linux password cannot replace it. |
| Installed services and configuration | Hub bootstrap/enrollment commands and site installer already deployed; matching centers and receiver identities configured; protected storage available; private tmpfs staging and encrypted or disabled swap. |

Ansible calls privilege elevation **become**. In this workflow that means sudo
to root. Its native variables `ansible_become_user` and
`ansible_become_password` retain their Ansible names. The legacy
`--ask-become-pass` option means **ask once for one shared sudo password**.
Prefer `--ask-sudo-password`, which asks separately for each reachable host.
Omit both only when the target accounts already have noninteractive sudo access.
Do not pass passwords with `-e`, save them in inventory, or paste them into chat.

## Enroll a configured site

1. Verify the controller's access and reviewed configuration before obtaining
   a Vault token. Replace `gc-09` consistently with the intended site:

   ```bash
   devenv shell vault-site-preflight gc-09 --controller
   devenv shell check-connectivity gc-09
   devenv shell check-connectivity gs-02
   ```

   The preflight is local and read-only. It checks inventory, source cleanliness,
   evaluated configuration, receiver identities and SSH pins. The connectivity
   command checks SSH and remote command execution, not sudo or Vault access.
   A reachable machine from another laptop is not proof of controller access.

2. Have the Vault custodian confirm that the existing Vault is initialized and
   unsealed, then provide a short-lived enrollment token using the approved
   private handoff. See the Vault access procedure below. LuxNix does not
   provision a human login method or an enrollment-administrator policy: the
   Vault owner must establish those first. A bare `vault token create` is not
   the enrollment procedure and can inherit the issuing token's broad policy.

3. Run from the controller's normal administrator shell:

   ```bash
   devenv shell enroll-reachable-hub-sites --site gc-09 --ask-sudo-password
   ```

   Enter the Linux sudo password for each host named in the hidden prompts.
   Then review the displayed target scope, hub address, revision and lock digest
   before entering the **Vault enrollment token**. No token prompt is shown if
   no site passes prerequisites. Use `--help` to inspect options without connections.

4. Read the per-site results. `enrolled` means credential installation,
   authentication, certificate and key checks, database node provisioning, and
   application/transfer-worker startup succeeded. Starting workers may resume
   queued work. It does not approve clinical recordings or prove a completed
   transfer. Complete the deployment acceptance checks below.

To consider all configured active sites, omit `--site`. Selection is the
intersection of `active_clients`, `gpu_client` and `endoreg_client`. Unreachable
sites are reported separately and can be retried later. A run fails if no site
enrolls or any selected reachable site fails. Correct the first reported blocker
and rerun the same scoped command: valid credentials and saved bundles are reused.
Do not delete identities to force a retry. Enrollment does not activate a new
NixOS configuration or rotate existing node secrets, salts or media keys.

## Troubleshooting enrollment

| Result or message | Check and next action |
| --- | --- |
| SSH connection closed / connection timed out | Check controller VPN route, SSH login account, authorized controller public key and server host-key pin. `unreachable` does not prove the host is powered off. A sudo password or new Vault token cannot repair SSH. |
| Incorrect sudo password / failed-prerequisite | Use the Linux password for the named target account, not the controller's password. Use `--ask-sudo-password` for differing passwords. Also verify that `/dev/shm` is tmpfs. |
| failed-connectivity | Inspect the failed remote command and configured Python interpreter. Ansible's ping module tests remote execution; it is not an ICMP network ping. |
| failed-preflight | Correct the reported inventory, receiver center, source-state or trust mismatch before issuing credentials. |
| Vault connection refused at 127.0.0.1 | Set `VAULT_ADDR` and `VAULT_CACERT` in the shell actually running Vault. Environment settings in a different shell do not apply. |
| Vault sealed | Ask the custodian to unseal the existing Vault. Never initialize it again as an access repair. |
| Vault permission denied | Verify the token's approved policy and lifetime with its issuer. Do not substitute an unrestricted root token. |
| failed-enrollment | Inspect the first failed task and restricted service logs. Saved bundles remain available for retry; re-enrollment is not breach recovery. |

## Expired site client certificate

On the site, inspect public certificate dates and renewal state:

```bash
sudo openssl x509 -in /var/lib/lx-annotate/hub-pki/client.crt -noout -dates
sudo luxnix-vault-enrollment-status
systemctl list-timers 'luxnix-vault-issue-hub-client-certificate*' --all
```

Restore Vault availability and valid AppRole authentication first. After correcting
the blocker, restart `vault-auth-setup.service` and require enrollment status
`ready`, then restart `luxnix-vault-issue-hub-client-certificate.service` and
start its timer. Verify the renewed certificate and transfer worker dependencies.
An enrollment deferral is for initial provisioning; do not retain it to suppress
renewal failures. Never write the enrollment status file manually.

## Transfer health failures after activation

The export health service checks the persisted export ledger. Payload rejection
can remain even when Vault, certificates and node provisioning are healthy.
Read the application journal before changing credentials:

```bash
sudo journalctl --namespace=+lx-annotate -u lx-annotate-hub-export-health.service -n 30 --no-pager
```

Use the export overview to inspect the recording's blocker. Complete metadata,
anonymization and segment review, then wait for cleanup and export proof. For
missing frame provenance on otherwise usable media, use **Frame-Herkunft
reparieren** in Hub Export. Preview and explicitly save an unresolved mapping;
available original timestamps and known recording start/end remain in endoreg-db.
This permits an otherwise eligible transfer while disabling electrical-data
matching. It does not clear cleanup failures or content mismatches. See the
[backend recovery contract](https://github.com/wg-lux/endoreg-db/blob/main/docs/video_storage_normalization.md#recover-usable-media-with-unresolved-frame-mapping).
Deploy matching shared contracts and applications on both sender and receiver. Never invent provenance,
set readiness flags in SQL, delete failed ledger entries or bypass clinical review.
Salt rotation does not reconstruct provenance or complete review gates.

Retry the existing transfer only after eligibility and payload checks pass.
Preserve its identity and audit history. Verify a matching receiver receipt for
the current artifact, then rerun the export health service and require zero
critical failures. A historical completion does not validate changed media.
See the [clinical transfer guide](clinical-hub-transfer-guide.md) and
[application export workflow](https://github.com/wg-lux/lx-annotate/blob/main/docs/guides/hub-export-workflow.md).

## Application interface requirements

The application owns these changes; LuxNix supplies runtime and worker health.
Extend the existing overview and backend contracts instead of creating a second
readiness implementation.

1. Add a **Needs action** filter with counts and a per-row **Next step** button.
   Include videos without transfer jobs. Distinguish processing, anonymization
   review, segment review, cleanup, identity evidence, provenance, integrity,
   operator marking and transport readiness. A generic “not ready for export”
   does not tell the operator which page or person can resolve the blocker.
2. Return structured blocker codes and allowed actions from shared backend
   validators. The current `resolve_video_hub_export_state` checks approval and
   artifact/hash readiness; it does not establish every payload requirement.
   A stored `persisted_verified` state must not imply that all current payload
   checks passed. Add a guarded complete preflight using the
   same identity/provenance/payload rules as the sender, with media leases where
   required; distinguish stored metadata from freshly verified bytes. Preflight
   must not mark, approve, reset or queue a video.
3. Deep-link **Review anonymization**, **Review segments**, **Check export
   readiness** and **Repair processing** to the selected video, retaining the
   originating filter and a return link. Add ID selection to the repair overview
   if needed; do not rely on filenames as identifiers. Missing originals block source reprocessing but permit explicit unresolved
   provenance acknowledgment. Missing identity evidence still requires
   **Request administrator recovery**.
4. Show cleanup task age, last observed progress, queue/worker availability and
   whether the task is actually observed. Preserve “unknown” when inspection
   cannot establish liveness. Provide a permission-checked **Inspect recovery**
   preview for old queued/running jobs. Reuse the existing job dispatcher and
   operation guards after review; it can expire old histories and roll back
   frame artifacts, so this must not be an automatic UI timeout or bulk reset.
5. Keep preflight, clinical approval, marking and sending separate. Show the
   specific reason beside a disabled action, support keyboard focus, announce
   asynchronous completion/errors, and preserve selection after refresh. Display
   workflow stages as stages; the existing percentage must not imply bytes sent.
   Completion requires the matching receiver receipt for the current artifact.

Implementation entrypoints in LX-Annotate are
`frontend/src/components/Export/HubExportOverviewComponent.vue`,
`frontend/src/stores/hubExportStore.ts`,
`frontend/src/components/VideoExamination/VideoExaminationAnnotation.vue`,
`frontend/src/components/Anonymizer/VideoBackfillRepairPanel.vue`,
`frontend/src/router/index.ts`, and `lx_annotate/hub/hub_export_state.py` /
`hub_export_payloads.py`. Reuse endoreg-db's
`services/annotations/segment_validation_workflow.py` and
`services/jobs/video_post_validation_jobs.py` for cleanup semantics.

Acceptance tests should cover a stored-ready video with missing provenance, a
missing-original acknowledgment and source-reprocessing refusal, missing identity hashes, completed cleanup
without export proof, stale versus live jobs, permission-denied actions, and a
video with no outbound job. Verify deep-link selection and keyboard navigation;
preflight must not change approvals or queue work, and retry must preserve the
existing transfer identity. The provenance-recovery panel is shared by the video examination and Hub Export
pages; its source implementation requires matching application and contract releases.

## Identities and keys

The deployment uses independent credentials for independent purposes. Do not
substitute one for another.

| Material | Purpose | Authoritative location | May leave that location? |
| --- | --- | --- | --- |
| Vault Shamir unseal shares | Unlock Vault after a restart | Authorized custodians | Never install on `gs-02` or any site node |
| Vault enrollment token | Reconcile PKI, AppRole, and node secrets | Operator session on `gs-02` | No; unset immediately after use |
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

## 1. Check and unseal Vault (custodian procedure)

In this deployment, `gs-02` is configured as the central hub. On a trusted
`gs-02` session, set the local authenticated endpoint before checking state:

First run **only** this command and wait for the root shell prompt:

```bash
sudo -i
```

Then run the following **inside that root shell**. Do not paste `sudo -i` and
these commands together: they can run in the original shell after root exits.
A successful Linux sudo login does not authenticate to Vault.

```bash
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

### Obtain a short-lived `VAULT_TOKEN`

An unseal share is not a Vault login credential and cannot be used as
`VAULT_TOKEN`. The person creating the enrollment token must first have an
existing Vault token that is authorized to create tokens for an approved
enrollment-administration policy. LuxNix does not currently create a human
authentication method or prescribe that policy's name. If no such issuer token
and reviewed policy exist, stop and ask the Vault owner to establish them; do
not reuse an AppRole Secret ID, site token, or unseal share.

On a trusted `gs-02` root shell, set `ENROLLMENT_POLICY` to the policy name
approved by the Vault owner. Then enter the authorized issuer token only at the
hidden prompt. The following replaces the powerful issuer token in the shell
immediately with a non-renewable enrollment token whose lifetime has a hard
30-minute maximum:

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

If policy lookup or token creation fails, immediately run
`unset VAULT_TOKEN enrollment_token ENROLLMENT_POLICY` and stop. Do not proceed
with an empty token or leave the issuer token exported.

Review the lookup metadata before continuing. It must show the approved policy,
a positive TTL no greater than 30 minutes, and `renewable false`. The lookup
projection excludes the token ID; never print the full token lookup response.
The approved enrollment policy must explicitly permit `auth/token/lookup-self`
and `auth/token/revoke-self`, since this token excludes the default policy.
Token creation fails with `permission
denied` when the issuer is not allowed to assign the requested policy; that is
an authorization blocker, not a reason to use the initial root token casually
or weaken the policy.

For the manual procedures below, keep the token only in this shell environment.
For controller enrollment, use the approved private handoff to its hidden prompt;
the wrapper deliberately ignores an inherited `VAULT_TOKEN`. The custodian
retains a trusted session for revocation. Do not pass it as a command-line
argument, save it in `~/.vault-token`, write it to a file, paste it into chat,
or enable shell tracing. When bootstrap or enrollment is complete, revoke it
before closing the shell:

```bash
vault token revoke -self
unset VAULT_TOKEN ENROLLMENT_POLICY
```

If the token expires first, subsequent Vault commands fail closed and a new
token must be issued through the same procedure. Do not renew this token.
The TTL, explicit maximum, policy, non-renewable, and output-field flags are
documented in HashiCorp's
[`vault token create` reference](https://developer.hashicorp.com/vault/docs/commands/token/create).

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

It permits that site's NixOS switch before AppRole files arrive. When
LX-Annotate uses its preserved local application master key rather than
Vault-managed encrypted storage, the base application may start, but the
certificate issuer, transfer worker, node provisioning, and envelope-key
preflight remain inactive until enrollment. It never permits hub transfer
without its required secrets. The value must not be placed in
`group_vars/gpu_client.yml`: enrollment state belongs to one machine, and an
unfinished site must not weaken the rest of the fleet.

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

Back on `gs-02`, obtain a short-lived administrative token as in step 1, then:

```bash
install -d -m 0700 /root/vault-enrollment
luxnix-vault-enroll-hub-site \
  <host>.intern /root/vault-enrollment/<host>
vault token revoke -self
unset VAULT_TOKEN ENROLLMENT_POLICY
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

The repository now provides a concrete delivery workflow from the trusted hub
staging directory to one site:

```bash
devenv shell check-connectivity gs-02
devenv shell check-connectivity <host>
devenv shell deliver-hub-enrollment --limit <host> \
  -e enrollment_expected_ca_sha256=<independently-verified-fingerprint>
```

Run from the exact clean, reviewed deployment checkout after recording operator
approval. The bundle must be in `/root/vault-enrollment/<host>` on `gs-02` and
the fingerprint must come independently from trusted hub state. The playbook
reruns local site preflight, requires pinned SSH identities for both connections,
reads protected hub files through SSH, relays the bundle through private tmpfs,
installs it with the fingerprint-pinned site installer, and installs the matching
hub node secret. It suppresses secret logs/diffs and removes ephemeral site
staging even after failure. Ansible's copy action creates plaintext temporary
files: the wrapper confines controller temporaries to an owner-only mode-`0700`
tmpfs directory and cleans them after success or failure. It refuses a missing,
shared or disk-backed runtime directory. The controller must be trusted, and
swap must remain encrypted or disabled under the existing host storage policy.
After an uncatchable process crash, remove any retained private runtime staging
before ending the incident. This replaces the manual copy/install steps below when
used successfully; continue with activation and acceptance in step 6.

The hub source directory is retained for operator-controlled recovery and must
be removed after acceptance under the credential-retention procedure. Delivery
does not restore a contained identity or start consumers. If delivery fails
partway, keep transfers contained and rerun before any consumer activation.

For manual delivery instead of the automated playbook, install the receiver copy of the node secret on
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
sudo luxnix-vault-install-hub-site-enrollment \
  /root/vault-enrollment/<host> \
  '<fingerprint-obtained-independently-from-gs-02>'
sudo luxnix-vault-enrollment-status
```

The installer validates every required input without printing credential
contents, rejects symlinks and empty files, verifies the independently supplied
Vault CA fingerprint and CA constraints, then atomically installs the four
site files with the ownership and modes below. It does not start services.

The resulting static enrollment files have these contracts:

| Path | Owner | Mode |
| --- | --- | --- |
| `/etc/secrets/vault/hub-pki/` | `root:sensitiveServices` | `0750` |
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
# On gs-02, from the reviewed checkout
sudo nixos-rebuild switch --flake .#gs-02 --accept-flake-config
sudo systemctl restart lx-annotate-hub-node-provisioning.service

# On the site, replace <host> with its explicit flake hostname
sudo nixos-rebuild switch --flake ".#<host>" --accept-flake-config
sudo systemctl reset-failed vault-auth-setup.service
sudo systemctl restart vault-auth-setup.service
```

If a site configuration was deliberately switched before its enrollment files
arrived, `vault.client.auth.deferUntilProvisioned = true` makes the missing-file
case a non-failing systemd condition. The base application may run when its
local secret and storage contracts are satisfied, but hub transfer remains
fail-closed.
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
  /etc/secrets/vault/hub-pki \
  /etc/secrets/vault/hub-pki/approle_role_id \
  /etc/secrets/vault/hub-pki/approle_secret_id \
  /etc/secrets/vault/hub-pki/source-node-secret \
  /var/lib/lx-annotate/hub-pki/client.crt \
  /var/lib/lx-annotate/hub-pki/client.key \
  /etc/secrets/vault/hub-pki/hub-recipient-current.pub.pem
sudo -u endoreg-service-user test \
  -r /etc/secrets/vault/hub-pki/source-node-secret
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
   sudo nixos-rebuild switch --flake .#gs-02 --accept-flake-config
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

Use the incident checklist in
`secrets-management.yml` at the repository root to distinguish routine
replacement from breach containment. Re-enrollment is not a complete breach
rotation: it creates another Secret ID, preserves an existing node shared
secret, and does not invalidate previously issued tokens or certificates.
Secret IDs currently have unlimited lifetime and reuse; the custodian must
retain a restricted accessor inventory and explicitly destroy superseded IDs.
Vault documents separate
[Secret ID accessor destruction](https://developer.hashicorp.com/vault/api-docs/auth/approle#destroy-approle-secret-id-accessor)
and [token revocation](https://developer.hashicorp.com/vault/docs/commands/token/revoke)
operations. Neither should expose the credential value in command arguments.

Certificate issuance now obtains a fresh AppRole token directly from the
protected enrollment files whenever issuance is needed; it does not reuse the
cached bootstrap token. Token lifetimes remain bounded. Offline retention accepts
only an unexpired certificate matching its private key. When replacing AppRole
files, explicitly restart bootstrap authentication and the dependent enrollment
chain under the approved maintenance procedure so other Vault consumers also
adopt the replacement; a plain start of an already-active unit is insufficient.

### Interactive routine AppRole replacement

After the custodian prepares a fresh `/root/vault-enrollment/gc-02` bundle on
`gs-02` using the enrollment procedure in section 4, run from a clean reviewed
deployment checkout in an interactive terminal:

```bash
devenv shell rotate-hub-enrollment --limit gc-02 \
  -e enrollment_expected_ca_sha256='<independently-verified-CA-fingerprint>'
```

Substitute the intended site for `gc-02`. The command runs site preflight and
hub/site connectivity checks, displays both addresses, the source revision and
the `flake.lock` digest, then requires `rotate gc-02` before delivery. Confirm
that the bundle is newly prepared and the node shared secret is unchanged.
Declining or running without a terminal stops before delivery.

The workflow reuses fingerprint-pinned enrollment delivery, restarts
`vault-auth-setup.service` even when already active, requires enrollment state
`ready`, restarts `managed-secrets-setup.service`, and invokes
`luxnix-vault-reissue-hub-client-certificate`. It checks the certificate unit's
result rather than requiring an issuing oneshot to remain active. On failure it
stops and displays classified enrollment guidance: replace rejected AppRole
material, migrate a changed CA through authenticated fingerprint verification,
unseal Vault on the hub, or repair connectivity as indicated. A `ready` state
with failed issuance requires inspecting the certificate service journal.

After successful activation, verify receiver acceptance and a disposable
transfer before revoking retiring Secret IDs/tokens and removing protected
staging. This command does not generate or revoke credentials, rotate the node
shared secret, or release containment. For incident rotation or changed node
secrets, use the coordinated procedure below. Password rotation remains a
separate workflow.

### Incident rotation boundaries

During an incident, isolate the affected site at trusted network and receiver
boundaries before issuing replacements. Stopping a worker on a compromised
machine is insufficient containment. Prevent new Vault issuance, revoke issued
tokens, replace the node secret in Vault and both local copies, and verify that
the receiver rejects old credentials before restoring transfer access. Do not
reconcile/re-enroll an identity while its containment depends on a disabled
policy that reconciliation would restore.

The receiver now requires an authenticated
[client CRL](https://nginx.org/en/docs/http/ngx_http_ssl_module.html#ssl_crl).
`luxnix-hub-crl-bootstrap.service` must publish a complete signed CRL set before
Nginx starts. `luxnix-hub-crl.timer` refreshes every 60 seconds; successful refresh
reloads Nginx, while fetch, validation or reload failure closes the transfer gate
with HTTP 503. Browser traffic on an already-running Nginx remains available.
Initial rollout requires unsealed Vault, provisioned trust and reachable CRL
endpoints; otherwise Nginx startup fails closed.

Defaults use the direct authenticated Vault VPN endpoint and existing server CA.
If the pinned client chain has multiple issuers, configure every complete CRL
endpoint under `hub.transferApi.crlUrls` in canonical YAML. Signatures, issuer
coverage, CRL numbers and freshness are checked before atomic publication.
The default maximum CRL age is 72 hours; `nextUpdate` is also enforced. For a
shorter hard bound, have the custodian configure shorter Vault CRL expiry and
automatic rebuild, then lower `crlMaxAgeSeconds`. Do not merely shorten the
client limit against an unchanged publisher. A stopped timer is an operational
fault; certificate expiry/CRL expiry remain the final bound until it is repaired.
TLS resumption is disabled on the transfer virtual host and transfer keepalive
is restricted. Graceful reload does not terminate in-flight requests, so retain
trusted network/application containment during an incident.

### Scoped breach containment and replacement

After trusted receiver/network containment, use an authorized short-lived
custodian token on the authoritative hub:

```bash
luxnix-vault-site-lifecycle contain <host>.intern
luxnix-vault-site-lifecycle rotate <host>.intern \
  --output-directory /root/vault-enrollment/<host>
```

The output directory must not already exist. Preserve prior incident evidence
under a separate protected name before preparing the canonical delivery path.
Containment first denies the site's Vault policy, destroys its Secret IDs and
revokes matching service-token accessors. It records durable state under
`/var/lib/luxnix-vault-site-lifecycle`; ordinary enrollment/reconciliation refuses
to undo it. Rotation uses KV compare-and-set and creates a new complete bundle
while the policy remains denied. On partial failure, contain again and generate
another fresh bundle. Serialize other direct Vault administration sessions;
they do not participate in the helper's lock.

The custodian policy needs scoped PKI/AppRole/KV mutations plus token-accessor
list, lookup and revocation rights. This is more privileged than routine
enrollment, so do not grant it to site AppRoles. Existing batch tokens are not
accessor-enumerable: establish their absence or bounded expiry before restoring
the policy. The helper configures new site tokens as service tokens but cannot
retroactively change old token types.

Revoke each affected public certificate serial through the Vault PKI revoke
endpoint (`vault write lx-hub-pki/revoke serial_number=<serial>`), refresh the hub
CRL service, and verify that the old certificate fails at the receiver. Deliver
the new bundle with the command above and explicitly restart
`lx-annotate-hub-node-provisioning.service` on both hosts to reprovision both
node records. Verify old credentials fail while
trusted receiver/network containment remains in place. Then explicitly release
the Vault containment marker and restore that one policy:

```bash
luxnix-vault-site-lifecycle resume <host>.intern --accept-consumer-verification
luxnix-vault-reconcile-hub-sites <host>.intern
```

Now restart site authentication and managed secrets, then run
`sudo luxnix-vault-reissue-hub-client-certificate` on that site. This explicit
root-only command bypasses a still-valid cached certificate and forces fresh
authentication and issuance. Its runtime marker remains after failure and is
removed only after the new files are installed; after a reboot, rerun the command
while containment remains. Verify new identity acceptance and a disposable transfer before
removing receiver/network containment. Revoke the Vault enrollment token afterward.
These steps do not revoke application/database sessions or rotate encryption
master keys. Record containment and recovery timestamps in the incident record.

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

## Controller SSH authorization

`hub_enrollment_admin_access` in the inventory scopes the existing `gs-02`
administrator public key to `gs-02`, `gc-06` and `gc-09`. Its group YAML supplies
`services.ssh.authorizedKeys` for generated NixOS configuration. The key is
restricted to connections from `172.16.255.22` and has SSH forwarding and PTY
allocation disabled; Ansible command execution remains available.

For initial access from a controller that already has administrator access, use
`ansible/playbooks/deploy_hub_admin_access.yml` through the protected playbook
wrapper with an explicit limit, for example `--limit gc-06`. Supply the current sudo password
through Ansible's hidden sudo-password prompt (`--ask-become-pass`), never a literal command
argument. The playbook appends the same public key to each administrator's
persistent `~/.ssh/authorized_keys`, preserves other keys, and protects the SSH
directory/file with modes 0700/0600. It does not copy private keys, restart SSH,
activate NixOS, or change sudo policy. Preview with `--check --diff` first.

Verify and record server host public keys through an existing trusted channel in `conf/ssh-host-keys/known_hosts`. Client host pins and
administrator login keys serve different purposes; both must be valid.

Removing this authorization requires removing both the declarative key and the
initial-access entry in `~/.ssh/authorized_keys`. Passwordless SSH does not imply
passwordless sudo: use the enrollment command's hidden `--ask-sudo-password` prompts when
root access requires a password.

## Implementation map

| File | Responsibility |
| --- | --- |
| `devenv/scripts.nix` and `devenv/commands.yml` | Expose and document the shell command. |
| `scripts/enroll-reachable-hub-sites.sh` | Restrict options and scope, enforce pinned SSH, optionally request the hidden sudo password. |
| `scripts/run-secret-playbook.sh` | Confine controller secret staging to private tmpfs and remove transient files. |
| `ansible/playbooks/enroll_reachable_hub_sites.yml` | Discover sites, prompt for the token, bootstrap the hub, deploy and verify each site, report failures. |
| `scripts/vault/site_enrollment_preflight.py` | Validate source, evaluated configuration, receiver identities and SSH pins. |
| `scripts/vault/ensure_site_enrollment.py` | Reconcile saved and installed identities against Vault; preserve valid credentials and reject conflicts. |
| `ansible/playbooks/tasks/hub_enrollment_sudo_password.yml` | Request each host's sudo password without logging or caching it. |
| `ansible/playbooks/tasks/hub_enrollment_reconcile.yml` | Run reconciliation using protected transport and temporary helpers. |
| `ansible/playbooks/tasks/hub_enrollment_delivery.yml` | Reuse the shared fingerprint-verified installation procedure. |
| `ansible/playbooks/deploy_hub_admin_access.yml` | Add the gs-02 public key without replacing existing administrator access. |
| `ansible/inventory/group_vars/hub_enrollment_admin_access.yml` | Declare the public key and source-address restriction. |
| `tests/test_vault_fleet_enrollment.py` | Exercise reconciliation, protected prompts, permitted wrapper options and failure reporting. |

The installed `luxnix-vault-*` commands come from
`modules/nixos/luxnix/vault/default.nix`;
find their exact definitions with `rg 'luxnix-vault-(bootstrap-hub-pki|enroll-hub-site|install-hub-site-enrollment)' modules`.
This workflow deploys credentials, not a new NixOS system generation. Changes to
boot-time service policy still require the normal reviewed NixOS rollout.
