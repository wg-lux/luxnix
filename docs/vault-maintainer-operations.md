# HashiCorp Vault Maintainer Notes

This is the first-response guide for maintainers of the HashiCorp Vault service
on `gs-02`. The independent LuxNix Ansible Vault uses `~/.lxv` and
`~/.lxv.key`; its password cannot unseal HashiCorp Vault.

Never place an unseal share, Vault token, `age` identity, AppRole Secret ID,
private key, or node shared secret in Git, chat, shell history, command
arguments, logs, or terminal transcripts.

## After a host or service restart

HashiCorp Vault starts sealed. This is expected. Connect through an already
trusted SSH session and use the VPN listener while retaining TLS hostname
verification:

```bash
sudo -i
export VAULT_ADDR=https://172.16.255.22:8200
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
export VAULT_TLS_SERVER_NAME=vault.endo-reg.net

systemctl is-active vault.service
vault status || true
```

Vault CLI exit status `2` means sealed. If Vault reports `Initialized true` and
`Sealed true`, an authorized custodian enters the required share only at the
hidden prompt:

```bash
vault operator unseal
vault status
```

Do not supply the share as a command argument. Do not run `vault operator init`
against existing storage.

After Vault is unsealed, restore and verify the dependent chain:

```bash
systemctl restart luxnix-vault-publish-hub-client-ca.service

systemctl is-active \
  vault.service \
  luxnix-vault-publish-hub-client-ca.service \
  nginx.service \
  lx-annotate-hub-node-provisioning.service
```

On every enrolled site, run `luxnix-vault-enrollment-status`, then verify the
authentication, managed-secret, certificate-issuance, provisioning, and
transfer-worker services listed in
[Vault Hub Machine Enrollment](vault-hub-machine-enrollment.md).

## Understand the three credentials

- The **unseal share** decrypts Vault's barrier after a restart. It is not an
  API token.
- A **Vault token** authorizes API operations. Routine bootstrap and enrollment
  use a short-lived administrative token, not the unseal share.
- The **LUKS or `age` credential** unlocks offline custody material. It is
  neither an unseal share nor a Vault token.

Validate a token without displaying it:

```bash
read -rsp 'Vault administrative token: ' VAULT_TOKEN
echo
export VAULT_TOKEN
vault token lookup
```

Clear it when finished:

```bash
unset VAULT_TOKEN
```

Generating a replacement root token is a break-glass, witnessed operation. It
requires the unseal threshold and must end with `vault token revoke -self`.
Do not improvise this procedure during an ordinary restart.

## If the unseal share appears lost

Stop before changing storage or initialization state.

1. Confirm Vault is initialized and sealed using `vault status`.
2. Contact every authorized custodian and check the custody register.
3. Check approved encrypted offline backups and removable custody media.
4. Look for an encrypted Raft snapshot together with its corresponding
   recovery material. A snapshot alone does not bypass the seal.
5. Record only non-secret evidence: timestamps, file metadata, checksums,
   fingerprints, and verification results.

If a valid share is recovered, follow
[HashiCorp Vault Owner Operations](vault-owner-immediate-actions.md). If no
share or independently recoverable backup exists, Vault's barrier-encrypted
contents cannot be recovered. Use the gated
[Vault Server Rebuild](vault-server-rebuild.md) procedure.

Key loss does not authorize stopping Vault, moving or deleting
`/var/lib/vault`, initializing a replacement, rotating the stable TLS CA, or
revoking dependent credentials. Those require the rebuild runbook's explicit
preservation, verification, impact-acceptance, and destructive-action gates.

## If a token is lost or rejected

An `invalid token` response is not an unseal problem. Confirm Vault is
unsealed, clear the rejected value with `unset VAULT_TOKEN`, and obtain a new
short-lived administrative token through the approved administrator auth
path. Never try the unseal share, custody passphrase, or Ansible Vault password
as an API token.

If no administrator auth path remains, conduct the documented witnessed
root-token generation ceremony using the required unseal threshold. Perform
only the approved recovery work and revoke the emergency root token
immediately afterward.

## Backup and custody expectations

- Keep encrypted unseal-share ciphertext root-only on the designated custody
  host and keep its decryption identity offline on LUKS-encrypted removable
  media.
- Keep another independently controlled offline recovery copy.
- Keep encrypted Raft snapshots and their decryption material separate from
  `gs-02` and from the unseal-share ciphertext.
- Test unseal custody and snapshot restoration at least quarterly.
- Prefer a multi-custodian threshold that tolerates loss of one share at the
  next approved rekey ceremony.

The detailed custody rules and seal/unseal commands are in
[HashiCorp Vault Owner Operations](vault-owner-immediate-actions.md).
