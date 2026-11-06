# LX-Annotate hub-export mTLS consumer enrollment

**Schema version:** 1

## Scope

**Consumer:** A LuxNix-managed LX-Annotate site node that exports to the central hub.

**Central vault:** `https://vault.endo-reg.net:8200`

**Central hub:** `https://gs-02.intern`

**Application boundary:** lx_annotate/views/hub_export.py is the operator-facing, session-authenticated API that queues exports. The Celery hub-transfer worker performs the actual HTTPS request and reads the mTLS certificate, private key, and server CA from its environment. Certificate enrollment therefore happens in LuxNix and Vault, not by calling a hub-export view.

## Security rules

- Never paste a Vault token, AppRole Secret ID, private key, or NetworkNode shared secret into a command argument, Git, logs, or chat.
- Use a short-lived scoped Vault administrative token; do not use or persist the initial root token.
- Deliver enrollment material only through the approved authenticated and encrypted channel.
- Verify the stable Vault server CA fingerprint from a trusted gs-02 session before installing it.
- Keep mTLS enabled. The NetworkNode shared secret is a second request-authentication factor and does not replace mTLS.
- Do not use curl -k, VAULT_SKIP_VERIFY, or a server leaf certificate as a CA trust anchor.

## Placeholders

**`SITE_SHORT_NAME`:** gc-11

**`SITE_FQDN`:** `gc-11.intern`

**`CENTER_KEY`:** replace-with-the-existing-center-key

## Walkthrough

### Step 1

**Actor:** `vault_owner_on_gs_02`

**Purpose:** Confirm that the central Vault is initialized, unsealed, and authenticated with its stable CA.

#### Shell

```bash
sudo -i
export VAULT_ADDR="https://172.16.255.22:8200"
export VAULT_CACERT="/var/lib/luxnix-vault-pki/ca.crt"
vault status
```

#### Expected

- Initialized is true.
- Sealed is false.

**If sealed:** An authorized custodian must run `vault operator unseal` and enter an unseal share at the hidden prompt. Never initialize an existing Vault again.

### Step 2

**Actor:** `vault_owner_on_gs_02`

**Purpose:** Bootstrap the dedicated client-only PKI and enroll the consumer identity.

#### Shell

```bash
read -rsp "Short-lived Vault admin token: " VAULT_TOKEN
echo
export VAULT_TOKEN

luxnix-vault-bootstrap-hub-pki

SITE_FQDN="gc-11.intern"
ENROLLMENT_DIR="$(mktemp -d /root/lx-hub-enrollment.XXXXXX)"
chmod 0700 "$ENROLLMENT_DIR"
luxnix-vault-enroll-hub-site "$SITE_FQDN" "$ENROLLMENT_DIR"

unset VAULT_TOKEN
find "$ENROLLMENT_DIR" -maxdepth 1 -type f -printf '%f\n' | sort
```

#### Expected files

- `approle_role_id`
- `approle_secret_id`
- `client-ca.pem`
- source-node-secret
- `vault-server-ca.pem`
- `vault-server-ca.sha256`

#### Notes

- The enrollment command creates a per-site AppRole and a client-only PKI role for the exact SITE_FQDN.
- It does not issue the site's leaf certificate; the site issues and renews that certificate after AppRole login.

### Step 3

**Actor:** `vault_owner_on_gs_02`

**Purpose:** Record non-secret certificate evidence without displaying credentials.

#### Shell

```bash
openssl x509 \
  -in "$ENROLLMENT_DIR/vault-server-ca.pem" \
  -noout -subject -issuer -fingerprint -sha256
openssl x509 \
  -in "$ENROLLMENT_DIR/client-ca.pem" \
  -noout -subject -issuer -fingerprint -sha256
stat -c '%a %U:%G %n' "$ENROLLMENT_DIR" "$ENROLLMENT_DIR"/*
```

#### Expected

- The directory mode is 700 and enrollment files are mode 400.
- The printed Vault CA fingerprint matches vault-server-ca.sha256 and trusted gs-02 state.

### Step 4

**Actor:** `repository_operator`

**Purpose:** Enable the existing declarative Vault and outbound-transfer contract for the consumer.

**Configuration reference:** `ansible/inventory/group_vars/gpu_client.yml`

#### Required values

```yaml
vault.client.address: https://vault.endo-reg.net:8200
vault.client.caCertFile: /etc/secrets/vault/hub-pki/vault-server-ca.pem
vault.client.auth.method: approle
vault.client.auth.roleIdFile: /etc/secrets/vault/hub-pki/approle_role_id
vault.client.auth.secretIdFile: /etc/secrets/vault/hub-pki/approle_secret_id
vault.client.hubPki.enable: true
vault.client.hubPki.commonName: gc-11.intern
luxnix.lxAnnotateLocal.hub.outboundTransfer.enable: true
luxnix.lxAnnotateLocal.hub.outboundTransfer.requireMtls: true
luxnix.lxAnnotateLocal.hub.outboundTransfer.caFile: /etc/secrets/vault/hub-pki/vault-server-ca.pem
```

#### Shell

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
nix eval '.#nixosConfigurations.gc-11.config.system.build.toplevel.drvPath'
```

**Note:** Provision both NetworkNode records: gc-11 as site_node with the matching center and secret file, and gs-02 as central_hub with baseUrl https://gs-02.intern. Do not hand-edit generated host Nix files.

### Step 5

**Actor:** `site_operator`

**Purpose:** Install the out-of-band enrollment files before switching the NixOS configuration.

**Precondition:** The encrypted enrollment bundle has been authenticated and decrypted into a root-only staging directory.

#### Shell

```bash
sudo -i
STAGING_DIR="/root/received-gc-11-enrollment"
INSTALL_DIR="/etc/secrets/vault/hub-pki"

install -d -m 0750 -o root -g sensitiveServices "$INSTALL_DIR"
install -m 0400 -o root -g root \
  "$STAGING_DIR/approle_role_id" \
  "$INSTALL_DIR/approle_role_id"
install -m 0400 -o root -g root \
  "$STAGING_DIR/approle_secret_id" \
  "$INSTALL_DIR/approle_secret_id"
install -m 0644 -o root -g root \
  "$STAGING_DIR/vault-server-ca.pem" \
  "$INSTALL_DIR/vault-server-ca.pem"

EXPECTED_FINGERPRINT="$(tr -d '[:space:]' < "$STAGING_DIR/vault-server-ca.sha256")"
ACTUAL_FINGERPRINT="$(openssl x509 -in "$INSTALL_DIR/vault-server-ca.pem" \
  -noout -fingerprint -sha256 | cut -d= -f2 | tr -d '[:space:]')"
test "$ACTUAL_FINGERPRINT" = "$EXPECTED_FINGERPRINT"
printf 'Verified Vault server CA fingerprint: %s\n' "$ACTUAL_FINGERPRINT"
```

**Note:** The managed-secrets unit retrieves source-node-secret after AppRole login. Do not manually install client.crt or client.key from the enrollment bundle; no leaf certificate or private key is present there.

### Step 6

**Actor:** `vault_owner_on_gs_02`

**Purpose:** Install the matching request-authentication secret for hub-side NetworkNode provisioning.

#### Shell

```bash
sudo install -m 0640 -o root -g sensitiveServices \
  "$ENROLLMENT_DIR/source-node-secret" \
  /etc/secrets/vault/hub-pki/gc-11-source-node-secret
```

**Warning:** This shared secret authenticates application requests. It is not a TLS key and must never be substituted for the mTLS certificate identity.

### Step 7

**Actor:** `site_operator`

**Purpose:** Activate AppRole authentication, retrieve managed secrets, and issue the mTLS leaf certificate.

#### Shell

```bash
sudo nixos-rebuild switch --flake . --accept-flake-config
sudo systemctl reset-failed vault-auth-setup.service
sudo systemctl start vault-auth-setup.service
sudo systemctl start managed-secrets-setup.service
sudo systemctl start luxnix-vault-issue-hub-client-certificate.service

systemctl is-active \
  vault-auth-setup.service \
  managed-secrets-setup.service \
  luxnix-vault-issue-hub-client-certificate.service
luxnix-vault-enrollment-status
```

#### Expected

- All three units print active.
- Enrollment status reports ready rather than enrollment-pending, tls-trust-failed, vault-sealed, vault-unreachable, or auth-rejected.

### Step 8

**Actor:** `site_operator`

**Purpose:** Verify the issued identity, key match, permissions, and remaining lifetime without exposing the private key.

#### Shell

```bash
CLIENT_CERT="/var/lib/lx-annotate/hub-pki/client.crt"
CLIENT_KEY="/var/lib/lx-annotate/hub-pki/client.key"
CLIENT_CA="/var/lib/lx-annotate/hub-pki/client-ca.pem"

sudo openssl x509 -in "$CLIENT_CERT" \
  -noout -subject -issuer -dates -ext extendedKeyUsage
sudo openssl verify -CAfile "$CLIENT_CA" "$CLIENT_CERT"
sudo openssl x509 -in "$CLIENT_CERT" -noout -checkend 86400

CERT_PUBLIC="$(sudo openssl x509 -in "$CLIENT_CERT" -pubkey -noout \
  | openssl pkey -pubin -outform DER | sha256sum | cut -d' ' -f1)"
KEY_PUBLIC="$(sudo openssl pkey -in "$CLIENT_KEY" -pubout -outform DER \
  | sha256sum | cut -d' ' -f1)"
test "$CERT_PUBLIC" = "$KEY_PUBLIC"
sudo stat -c '%a %U:%G %n' "$CLIENT_CERT" "$CLIENT_KEY" "$CLIENT_CA"
```

#### Expected

- Certificate verification prints OK.
- The certificate and private-key public hashes match.
- The certificate has client authentication usage and is valid for more than one day.
- Runtime PKI files are root-owned and group-readable only by sensitiveServices.

### Step 9

**Actor:** `site_and_hub_operators`

**Purpose:** Restart provisioning and the transfer worker, then verify the complete path used by hub_export.py jobs.

#### Shell site

```bash
sudo systemctl restart lx-annotate-hub-node-provisioning.service
sudo systemctl restart lx-annotate-celery-hub-transfer-worker.service
systemctl is-active \
  lx-annotate-hub-node-provisioning.service \
  lx-annotate-celery-hub-transfer-worker.service
sudo systemctl show lx-annotate-celery-hub-transfer-worker.service \
  -p EnvironmentFiles --no-pager
```

#### Shell hub

```bash
sudo systemctl restart luxnix-vault-publish-hub-client-ca.service
sudo systemctl restart lx-annotate-hub-node-provisioning.service
systemctl is-active \
  vault.service \
  luxnix-vault-publish-hub-client-ca.service \
  nginx.service \
  lx-annotate-hub-node-provisioning.service
```

**End to end check:** Sign in to LX-Annotate as an operator, use the hub-export UI/API to queue one eligible anonymized processed video, and confirm that the outbound job succeeds and gs-02 records the request under NetworkNode gc-11. The operator endpoint uses the Django session; the worker subsequently uses HTTPS mTLS plus X-Network-Node-Key and X-Network-Node-Secret.


## Application runtime contract

**Require mtls env:** `LX_ANNOTATE_HUB_EXPORT_REQUIRE_MTLS=true`

**Client certificate env:** `LX_ANNOTATE_HUB_EXPORT_CLIENT_CERT_FILE=/var/lib/lx-annotate/hub-pki/client.crt`

**Client key env:** `LX_ANNOTATE_HUB_EXPORT_CLIENT_KEY_FILE=/var/lib/lx-annotate/hub-pki/client.key`

**Server ca env:** `LX_ANNOTATE_HUB_EXPORT_CA_FILE=/etc/secrets/vault/hub-pki/vault-server-ca.pem`

**Behavior:** The worker fails closed if the certificate or key is missing or unreadable, refuses non-HTTPS hub URLs, verifies the central hub with the configured server CA, presents the client certificate and key, and rejects redirects.

## Cleanup

**Actor:** `vault_owner_and_site_operator`

**Instruction:** After verified installation and any required custodian backup, securely remove plaintext staging directories on both machines using the approved secret-material disposal procedure. Do not remove active files under /etc/secrets/vault/hub-pki or /var/lib/lx-annotate/hub-pki.

## Troubleshooting

**`enrollment-pending`:** Verify that the AppRole files and Vault server CA exist at the configured paths.

**`tls-trust-failed`:** Re-check the stable Vault CA fingerprint from trusted gs-02 state; never disable verification.

**`vault-sealed`:** Ask an authorized Vault custodian to unseal the central instance.

**`auth-rejected`:** Rotate the site's AppRole Secret ID through the approved enrollment flow; do not expose it while diagnosing.

**Certificate issue failed:** Inspect `journalctl -u luxnix-vault-issue-hub-client-certificate.service -b --no-pager` for non-secret errors.

**Transfer 401 or 403:** Verify both the mTLS identity accepted by Nginx and the separately provisioned NetworkNode key/shared-secret pair.

## References

- `docs/vault-hub-machine-enrollment.md`
- `modules/nixos/luxnix/vault/default.nix`
- `modules/nixos/services/lx-annotate-local/README.md`
- `/home/admin/dev/lx-annotate/lx_annotate/views/hub_export.py`
- `/home/admin/dev/lx-annotate/lx_annotate/hub/hub_export_worker.py`
