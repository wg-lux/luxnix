# Hub Secret Delivery

Secrets that several hosts need (the Keycloak client secret, an allowlisted
center salt, any other shared or per-host credential) are published **once** on
the hub secrets server. Each enrolled host fetches them with its own scoped
token and keeps the last accepted value, so a sealed, restarting or unreachable
hub does not stop a site.

Nothing in this guide deploys or activates a host. Publishing, enrolling and
switching the backend are operator actions on named hosts.

## What a host needs

| Goal | Inventory (`host_luxnix` / `group_luxnix`) |
| --- | --- |
| Standard site client (address, CA pin, credential files, hub PKI) | `vault.client.hubSite.enable: "true"` |
| Token instead of AppRole credentials | `vault.client.hubSite.auth: '"token"'` |
| Fetch a shared secret | `vault.client.secrets.<name>.restartUnits: [ '"my.service"' ]` |
| Fetch a secret only this host may read | `vault.client.secrets.<name>.scope: '"host"'` |
| Keycloak client secret for LX-Annotate | `luxnix.lxAnnotateLocal.django.keycloakSecretViaVault: "true"` |
| Allowlisted center identity salt | `luxnix.lxAnnotateLocal.django.centerIdentitySalt: "true"` |
| Keep running through hub outages | `vault.client.allowOffline: "true"` (default for EndoReg clients) |
| Use OpenBao instead of Vault | `vault.backend: '"openbao"'` |

`hubSite.enable` only sets defaults; every explicit `vault.client.*` value still
wins, so existing group variables keep working unchanged. After changing
inventory run `devenv tasks run autoconf:generate`.

A declared secret `<name>` defaults to:

- KV record `lx-hub-secrets/shared/<name>` (or `lx-hub-secrets/hosts/<fqdn>/<name>`
  with `scope = "host"`), field `value`;
- file `/etc/secrets/vault/hub/<name>`, `root:<sensitive service group>`, mode `0640`;
- single-line content (`stripNewlines`; disable for PEM material).

`kvPath`, `field`, `path`, `owner`, `group`, `mode` and `required` override
these. Consumers reference the file path, for example through a Secretspec
`*_FILE` variable; see [Secretspec](#secretspec).

## Publishing a secret on the hub

On the hub, with `VAULT_ADDR` and a short-lived administrative `VAULT_TOKEN`
in the environment (the same variables for Vault and OpenBao):

```bash
luxnix-vault-publish-secret --shared smtp_password             # hidden prompt
luxnix-vault-publish-secret --host gc-10.intern backup_key < key.txt
luxnix-vault-publish-secret --shared ca_bundle --multiline < bundle.pem
```

The value is read from the prompt or standard input, never from the command
line. Publishing the same value again changes nothing. A different value is
refused unless `LUXNIX_VAULT_ALLOW_SECRET_ROTATION=1` is set, and is written
with check-and-set against the version that was read, so two operators cannot
silently overwrite each other.

The Keycloak client secret keeps its dedicated command
(`luxnix-vault-publish-oidc-client-secret`) and rotation gate, described in
[Coordinated Secret Rotation](secret-rotation.md). Center salts are created only
by `luxnix-vault-reconcile-hub-sites` for centers listed in
`vault.server.hubPki.sharedIdentityCenters`; see
[Center Identity Salt Activation](center-identity-salt-activation.md).

## Who may read what

`luxnix-vault-reconcile-hub-sites <fqdn>` writes one policy per site. It grants
read access to exactly:

- `shared/*`: records every enrolled host may read;
- `hosts/<fqdn>/*`: records of that host only;
- the site's node secret, the hub recipient public key, the Keycloak client
  secret and, for allowlisted centers, that center's salt.

Run the reconcile command again for existing sites after updating the hub so
their policies gain the `shared/` and `hosts/` paths. Put a secret under
`shared/` only if every enrolled host may know it.

Containing a site (`luxnix-vault-site-lifecycle`) replaces its policy with a
deny rule. That stops AppRole logins and per-host tokens alike. Values a host
already fetched stay on that host; rotate them at their owner.

## Host credentials

**AppRole (default).** `luxnix-vault-enroll-hub-site` produces the enrollment
bundle and `luxnix-vault-install-hub-site-enrollment` installs it, as described
in [Machine Enrollment](vault-hub-machine-enrollment.md). Every fetch logs in
afresh and receives a token valid for one hour.

**Token.** For hosts configured with `hubSite.auth = "token"`:

```bash
# hub
luxnix-vault-issue-site-token gc-10.intern /root/vault-enrollment/gc-10-token
# host, after transferring the directory through an approved channel
luxnix-vault-install-site-token /path/to/gc-10-token <server-ca-sha256-fingerprint>
systemctl start vault-auth-setup.service luxnix-hub-secrets.service
```

The token is bound to the site policy and renewed by the host at every refresh.
A host that stays offline longer than `vault.server.hubPki.siteTokenPeriod`
(default 768 hours) needs a new token. The hub-transfer client certificate
renewal still uses AppRole when `auth.method = "approle"`; a token-only host
renews it with the token from `vault-auth-setup`.

## What happens during a hub outage

`luxnix-hub-secrets.service` runs at boot and then every
`vault.client.refreshInterval` (default 15 minutes). For each secret it decides:

| Hub answer | Result |
| --- | --- |
| Valid value, version not older than the accepted one | Deployed atomically; `restartUnits` are restarted only if the content changed |
| Unreachable, sealed, or no token because login could not reach the hub | With `allowOffline`: the deployed value stays, a `BLOCKER` line names the state. Without: the run fails |
| Permission denied, TLS trust failure, malformed or empty answer, missing record | Never replaced by the cache: the run fails and the deployed file is untouched |
| Version older than the accepted one | Rejected as a stale answer |
| No value was ever deployed | Fails (or stays absent for `required = false`) until the hub answers |

The Keycloak client secret, the node secret, the recipient public key and the
center salt use the same decision through `managed-secrets-setup`.

```bash
luxnix-hub-secrets-status        # names, KV paths, accepted versions, times
journalctl -u luxnix-hub-secrets.service
```

The status shows metadata only. After a reviewed deletion and re-creation of a
KV record (its version restarts at 1), remove
`/var/lib/luxnix-hub-secrets/<name>.json` on the affected hosts.

Limits: a host that has never fetched a secret cannot start its consumer during
an outage. Outage tolerance also does not make the hub highly available; the
OpenBao hub is a single node that needs its unseal ceremony after every
restart. Managed TLS leaf renewal reloads it without a restart.

Managed-secret generators authenticate afresh through the same AppRole helper
as periodic delivery. They do not reuse the boot-time token, which can expire
before an application upgrade or service restart. A rejected identity still
fails closed; only sealed or unreachable hub states may reuse an existing
value when `allowOffline` permits it. No credentials or key identities are
replaced by this refresh. For an already stopped host, restart the reviewed
managed-secrets unit and then the application startup chain after deploying the
fix; a still-rejected fresh login requires the enrollment recovery workflow.

## Switching the hub to OpenBao

`vault.backend` selects the product for the hub server, every hub tool and
every client. The default stays `"vault"`. With `"openbao"`:

- the hub runs `openbao.service` from `luxnix.openbao` with the listener
  address, API address and TLS material of `vault.server.*`;
- its state lives in `/var/lib/openbao`, which must be declared as an encrypted
  mount. It never opens the Vault Raft directory;
- all `luxnix-vault-*` commands and client units keep their names and call the
  OpenBao client; the `VAULT_*` variables and file handles are unchanged.

The two servers are never both authoritative. Follow the ordered gates in
[OpenBao Hub and Vault Migration](openbao.md): rehearse with
`devenv shell openbao-provision`, freeze writers, transfer the final delta, then
switch backend, endpoint, CA pin and fresh host credentials together. Host
credentials are not portable: enroll each site again against OpenBao.

## Secretspec

LX-Annotate loads its settings through Secretspec, which today receives **file
handles** such as `DJANGO_KEYCLOAK_CLIENT_SECRET_FILE`. Hub delivery keeps that
contract: it writes the files those variables point at. When Secretspec reads
OpenBao directly, the same records apply:

| Secretspec variable | Hub KV record | Field |
| --- | --- | --- |
| `DJANGO_KEYCLOAK_CLIENT_SECRET_FILE` | `lx-hub-secrets/oidc/endoregdb-api` | `client_secret` |
| `LX_ANNOTATE_HUB_SOURCE_NODE_SECRET_FILE` | `lx-hub-secrets/nodes/<fqdn>` | `shared_secret` |
| `LX_ANNOTATE_HUB_EXPORT_RECIPIENT_PUBLIC_KEY_FILE` | `lx-hub-secrets/hub/envelope-recipient/current` | `public_key` |
| center salt source for `DJANGO_IDENTITY_SALT_KEYRING_FILE` | `lx-hub-secrets/centers/<center>/identity` | `salt` |
| any declared secret | `lx-hub-secrets/shared/<name>` or `hosts/<fqdn>/<name>` | `value` |

The media master key, Django signing keys and machine identity salts stay
local to each host and are not published to the hub.

## Verification

```bash
python -m pytest -q tests/test_hub_secret_fetch.py tests/test_hub_secret_backend.py
devenv tasks run tests:openbao-vm
```

The first suite covers the outage decisions with a stand-in client and
evaluates hub and site under both backends. Publishing, a scoped token fetch,
sealing and shutdown were additionally exercised by hand against a disposable
OpenBao 2.6.5 development server. No production host was changed, and no
physical hub cutover or multi-host rehearsal has been performed.
