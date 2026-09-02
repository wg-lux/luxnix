# Vault Owner: Immediate Actions Required

This handoff is for the custodian of the `gs-02` Vault unseal key and the
original Vault implementation owner. The current operator does not need and
must not receive the unseal key, root token, or plaintext enrollment secrets.

Current verified state: Vault is initialized, uses a one-share/one-threshold
Shamir seal, and is sealed. Hub provisioning cannot continue while it is
sealed.

## 1. Unseal Vault personally

On `gs-02`, enter the saved unseal key only at Vault's hidden prompt:

```bash
sudo -i
export VAULT_ADDR=https://vault.endo-reg.net:8200
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
vault status
vault operator unseal
vault status
```

Required result: `Initialized true` and `Sealed false`.

Do not send the key to the current operator. If the key cannot be recovered,
stop and report that blocker. Do not run `vault operator init` again; doing so
would not recover the existing Raft-encrypted data.

## 2. Bootstrap and publish the hub CA

Obtain a short-lived administrative token using the issuer and revocation
procedure in
[`vault-hub-machine-enrollment.md`](./vault-hub-machine-enrollment.md#obtain-a-short-lived-vault_token),
then run:

```bash
luxnix-vault-bootstrap-hub-pki
vault token revoke -self
unset VAULT_TOKEN ENROLLMENT_POLICY

systemctl restart luxnix-vault-publish-hub-client-ca.service
systemctl is-active vault.service \
  luxnix-vault-publish-hub-client-ca.service
```

Both services must report `active`.

## 3. Review and deploy the AppRole leak fix

Before issuing replacement credentials, review and deploy the change in
`modules/nixos/luxnix/vault/default.nix` that sends AppRole credentials through
a mode-0600 JSON payload instead of process arguments. Its regression test is
in `tests/nixtest/vault_secret_delivery_contracts_test.nix`.

The previous `gc-02` Secret ID appeared in `systemctl status`; treat it as
exposed and rotate it. Apply the same controlled rotation to `gc-10` if its old
bootstrap implementation was executed.

## 4. Enroll and deliver the site bundles

After the safe client implementation is deployed, enroll every GC site:

```bash
for host in <inventory-enrolled-host-1> <inventory-enrolled-host-2>; do
  luxnix-vault-enroll-hub-site \
    "$host.intern" "/root/vault-enrollment/$host"
done
```

Deliver each site's AppRole files, `vault-server-ca.pem`, and
`source-node-secret` through the approved encrypted secret-delivery channel.
The server CA must come from `/var/lib/luxnix-vault-pki/ca.crt`; never deliver
the renewable server leaf as a trust anchor. Compare its SHA-256 fingerprint
with trusted local `gs-02` state during installation as described in
`docs/vault-hub-machine-enrollment.md`.
Install matching receiver copies on `gs-02` as:

```text
/etc/secrets/vault/hub-pki/<host>-source-node-secret
...
/etc/secrets/vault/hub-pki/<host>-source-node-secret
```

Use owner `root:sensitiveServices` and mode `0640` for the receiver copies.

## Non-secret confirmations

- Vault is unsealed.
- Hub PKI bootstrap completed.
- Client-CA publication is active.
- The safe AppRole implementation is deployed on every GC site.
- Old Secret IDs were revoked and replacement bundles were delivered.
- Receiver-side node-secret files were installed.
