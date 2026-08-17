# Add a Machine to Vault-Backed Hub Transfer

This runbook enrolls a new site node, written below as `<host>` (for example
`gc-11`), into the `gs-02` LX-Annotate hub. Run secret-handling commands as
`root`. Never put unseal keys, Vault tokens, AppRole Secret IDs, private keys,
or node shared secrets in Git, Nix, terminal arguments, logs, or chat.

## 1. Check and unseal Vault

On `gs-02`:

```bash
sudo -i
export VAULT_ADDR=https://vault.endo-reg.net:8200
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

## 2. Bootstrap the hub engines

Use a short-lived administrative token without placing it in shell history:

```bash
read -rsp "Temporary Vault admin token: " VAULT_TOKEN
echo
export VAULT_TOKEN
luxnix-vault-bootstrap-hub-pki
unset VAULT_TOKEN

systemctl restart luxnix-vault-publish-hub-client-ca.service
systemctl is-active vault.service \
  luxnix-vault-publish-hub-client-ca.service
```

The bootstrap is idempotent. It prepares `lx-hub-pki`, `lx-hub-secrets`, and
AppRole authentication. The client-CA publisher must become `active`.

## 3. Add the declarative YAML configuration

Add the site to `ansible/inventory/hosts.ini` and create or update
`ansible/inventory/host_vars/<host>.yml`. Use the existing `gc-10.yml` as the
full host example. The Vault and transfer-specific settings are:

```yaml
host_nixos:
  'networking.hosts."172.16.255.22"':
    - "vault.endo-reg.net"

host_luxnix:
  vault.client.enable: "true"
  vault.client.allowOffline: "false" # Re-Enable this when you dont have a root server set up for provisioning
  vault.client.address: '"https://vault.endo-reg.net:8200"'
  vault.client.caCertFile: '"/etc/secrets/vault/hub-pki/vault-server-ca.pem"'
  vault.client.auth.method: '"approle"'
  vault.client.auth.roleIdFile: '"/etc/secrets/vault/hub-pki/approle_role_id"'
  vault.client.auth.secretIdFile: '"/etc/secrets/vault/hub-pki/approle_secret_id"'
  vault.client.hubPki.enable: "true"
  vault.client.hubPki.commonName: '"<host>.intern"'

host_services:
  luxnix.lxAnnotateLocal.hub.outboundTransfer.enable: "true"
  luxnix.lxAnnotateLocal.hub.outboundTransfer.requireMtls: "true"
  luxnix.lxAnnotateLocal.hub.outboundTransfer.caFile: '"/etc/secrets/vault/hub-pki/vault-server-ca.pem"'
  luxnix.lxAnnotateLocal.hub.nodeProvisioning.enable: "true"
```

Add the site node to the site's `hub.nodeProvisioning.nodes`, together with the
`gs-02` central-hub entry. Also add it to the list in
`ansible/inventory/host_vars/gs-02.yml`:

```nix
{
  nodeKey = "<host>";
  displayName = "<host> site node";
  role = "site_node";
  centerKey = "<center-key>";
  sharedSecretFile = "/etc/secrets/vault/hub-pki/<host>-source-node-secret";
}
```

Validate and regenerate derived Nix configurations:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval '.#nixosConfigurations.<host>.config.system.build.toplevel.drvPath'
```

Do not hand-edit the generated `systems/x86_64-linux/<host>/default.nix`.

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

## 5. Install files before switching configurations

On the site, install the delivered files at these paths and modes:

| Path | Owner | Mode |
| --- | --- | --- |
| `/etc/secrets/vault/hub-pki/approle_role_id` | `root:root` | `0400` |
| `/etc/secrets/vault/hub-pki/approle_secret_id` | `root:root` | `0400` |
| `/etc/secrets/vault/hub-pki/vault-server-ca.pem` | `root:root` | `0644` |
| `/etc/secrets/vault/hub-pki/source-node-secret` | `root:sensitiveServices` | `0640` |

On `gs-02`, install a matching copy of the same `source-node-secret` as:

```text
/etc/secrets/vault/hub-pki/<host>-source-node-secret
```

Use owner `root:sensitiveServices` and mode `0640`. The site and hub copies
must match. Install these files before either host configuration references
them, otherwise the fail-closed services will stop activation.

After confirming delivery, securely remove temporary enrollment copies. Keep
only the approved custodian backup required by the credential policy.

## 6. Deploy and verify

During initial `gc-*` enrollment,
`vault.client.auth.deferUntilProvisioned = true` makes authentication failures
a non-failing systemd condition. The NixOS switch can finish, but
`vault-auth-setup.service` is deliberately inactive and LX-Annotate remains
fail-closed. Confirm this temporary state without printing secrets:

```bash
systemctl status vault-auth-setup.service
journalctl -u vault-auth-setup.service -b --no-pager
```

Expected before delivery: the unit reports that its start condition was not met,
not `failed`. The journal names missing paths and must not contain credential
values.

`luxnix-vault-enrollment-status` distinguishes `enrollment-pending`,
`tls-trust-failed`, `vault-sealed`, `vault-unreachable`, and `auth-rejected`.
An unclassified failure is reported as `vault-error`, never silently folded
into enrollment or TLS state. Dependent secret and certificate units load
`vault.env` optionally only so they can emit the recorded state themselves;
they still exit with an error and cannot start LX-Annotate when runtime
credentials are absent. No empty `vault.env` is created, and raw Vault errors
are not replayed into the journal.

After a stable-CA deployment or server-leaf rotation, use this order:

1. Vault starts and may report `vault-sealed`.
2. An authorized operator explicitly unseals it on `gs-02`; clients never hold
   an unseal key.
3. Start `vault-auth-setup.service`.
4. Start `managed-secrets-setup.service`.
5. Start `luxnix-vault-issue-hub-client-certificate.service` and then verify
   LX-Annotate.

Leaf renewal under the same stable CA requires no client CA replacement. A CA
change is a separate authenticated migration and must fail closed until the new
fingerprint has been verified from trusted `gs-02` state.

After installing all enrollment files, start the authentication chain:

```bash
sudo systemctl start vault-auth-setup.service
sudo systemctl start managed-secrets-setup.service
sudo systemctl start luxnix-vault-issue-hub-client-certificate.service
systemctl is-active vault-auth-setup.service
```

The last command must print `active`. After every active GC host has completed
enrollment, remove the temporary `vault.client.auth.deferUntilProvisioned`
setting from `ansible/inventory/group_vars/gpu_client.yml`, regenerate the host
configurations, and switch once more. From that point onward, missing
credentials and real Vault authentication errors fail activation normally.

Deploy `gs-02` first, then the site:

```bash
# On gs-02
nh os switch . -- --accept-flake-config
systemctl restart lx-annotate-hub-node-provisioning.service

# On the site
nh os switch . -- --accept-flake-config
systemctl reset-failed vault-auth-setup.service
systemctl restart vault-auth-setup.service
```

Verify without displaying file contents or credential values:

```bash
# Site
systemctl is-active \
  vault-auth-setup.service \
  managed-secrets-setup.service \
  luxnix-vault-issue-hub-client-certificate.service \
  lx-annotate-hub-node-provisioning.service \
  lx-annotate-celery-hub-transfer-worker.service

# Hub
systemctl is-active \
  vault.service \
  luxnix-vault-publish-hub-client-ca.service \
  nginx.service \
  lx-annotate-hub-node-provisioning.service
```

Finally perform one authenticated mTLS transfer from the new site and confirm
that `gs-02` records it under the expected `NetworkNode`.

## Migrate an already enrolled site to the stable server CA

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

## Rotation or removal

Normal Vault TLS renewal changes only the server leaf and key while preserving
the CA. Re-enrollment creates replacement AppRole material while preserving the
per-node Vault policy. Deliver and activate the replacement atomically, then
revoke the old Secret ID/token. To remove a machine, stop its transfer worker,
revoke its AppRole and certificates, remove its KV node secret, and deactivate
its `NetworkNode`. Treat removal as a separate reviewed operation; do not delete
Vault paths or receiver records during routine enrollment.
