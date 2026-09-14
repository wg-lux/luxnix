# Rebuild `gs-02` HashiCorp Vault After Loss of the Unseal Share

Use this runbook only after every authorized custodian and approved backup
location has been checked. An initialized Shamir-sealed Vault cannot recover
its Raft data without a valid unseal share. The LuxNix Ansible vault on
`gc-06` is independent and must not be deleted or regenerated.

Completing preparation does **not** authorize deletion of `/var/lib/vault`.

## Expected loss of functionality

A rebuild creates a new cryptographic trust domain. The old Vault contents,
leases, tokens, AppRoles, Secret IDs, policies, KV values, and internal PKI
cannot be recovered from the rebuilt service. Until reconstruction and
re-enrollment finish, dependent clients fail closed: managed-secret delivery,
hub client-certificate issuance, and authenticated hub transfer are
unavailable. Preserve the stable server TLS CA when possible; the internal hub
client CA is Vault data and will still be replaced.

## Roles and two-person gate

- The incident owner records that the share is irrecoverable and approves loss
  of the old Vault contents.
- A custodian retains the new unseal share and initial root token; the deploying
  operator must not retain copies.
- Two people verify the encrypted pre-rebuild archive before reset.
- Record only fingerprints, timestamps, results, and custodian names. Never
  record keys, tokens, Secret IDs, or node secrets.

## 1. Prepare without changing `gs-02`

On `gc-06`, preserve the independent Ansible state and verify decryption
without displaying plaintext:

```bash
stat /home/admin/.lxv /home/admin/.lxv.key /home/admin/.lxv/psk/gc-06.psk
ANSIBLE_CONFIG=/nonexistent ansible-vault view \
  --vault-password-file /home/admin/.lxv.key \
  /home/admin/.lxv/secrets/system_password/roles/postgres_host_main/postgres_host_main_password \
  >/dev/null
```

Build the intended `gs-02` generation before the outage:

```bash
nix eval '.#nixosConfigurations.gs-02.config.system.build.toplevel.drvPath'
nix build '.#nixosConfigurations.gs-02.config.system.build.toplevel'
```

On `gs-02`, inspect paths without printing contents:

```bash
sudo stat /var/lib/vault /var/lib/luxnix-vault-pki/ca.crt \
  /var/lib/luxnix-vault-pki/ca.key /var/lib/luxnix-vault-pki/server.crt \
  /var/lib/luxnix-vault-pki/server.key
sudo vault status || true
```

Preserve the stable server TLS CA to avoid an unnecessary server trust-anchor
migration. A new internal `lx-hub-pki` client CA will nevertheless be created,
so the published hub client CA and all site client certificates must change.

## 2. Create an encrypted preservation archive

Use an offline `age` recipient whose private key is not on `gs-02`. During an
approved outage:

```bash
sudo systemctl stop vault.service
sudo systemctl is-active vault.service # expected: inactive
sudo install -d -m 0700 /mnt/approved-encrypted-backup/vault-rebuild
sudo luxnix-vault-prepare-server-rebuild \
  --recipient 'age1<approved-offline-custodian-public-key>' \
  --output-directory /mnt/approved-encrypted-backup/vault-rebuild
```

The archive contains the old barrier-encrypted Raft directory, stable TLS
state, and receiver-side hub secrets when present. It is encrypted before it
is written. Move it to approved offline custody and independently verify its
SHA-256 manifest and successful decryption/listing on another trusted machine.
Archive creation alone is not sufficient verification.

If reset is not authorized, restart the unchanged sealed Vault:

```bash
sudo systemctl start vault.service
```

## 3. Destructive authorization gate

The change record must confirm all of these before any reset:

- no valid unseal share or recoverable snapshot with its keys exists;
- the encrypted archive was independently decrypted and inspected;
- loss of old leases, AppRoles, Secret IDs, policies, and internal PKI is accepted;
- `gc-02` and `gc-10` will fail closed until re-enrollment;
- the stable server CA fingerprint was recorded from trusted local state;
- custodians are present for the new share and initial token.

Deleting or moving `/var/lib/vault` is intentionally not automated. After
approval, use a reviewed host-specific procedure that moves the old directory
to a root-only quarantine path instead of immediately deleting it. Resolve and
record the exact path before performing that destructive operation.

## 4. Initialize the empty Vault

Start Vault only after an empty, correctly owned storage directory exists:

```bash
sudo systemctl start vault.service
export VAULT_ADDR=https://172.16.255.22:8200
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
export VAULT_TLS_SERVER_NAME=vault.endo-reg.net
vault status
umask 077
vault operator init \
  -key-shares='<approved-share-count>' \
  -key-threshold='<approved-threshold>'
```

The IP is the Vault listener on the AGLNet VPN. `VAULT_TLS_SERVER_NAME` retains
certificate hostname verification while avoiding the public DNS route from
`gs-02`.

The custodian captures the output directly into approved offline custody. Do
not redirect it to a file on `gs-02`, paste it into chat, or retain it in
terminal scrollback. Unseal through the hidden prompt:

```bash
vault operator unseal
vault status
```

Use the initial root token only to establish a short-lived administrative
path, then revoke it under the organization's token policy. Never persist it.

If the approved recovery design requires a copy of the new unseal share on
`gc-06`, encrypt the share for the designated recovery recipient before it
leaves the custodian boundary. Transfer only the ciphertext and install it in a
root-only directory on `gc-06`. The project convention is
`/root/vault-custody/gs-02-unseal-share-YYYY-MM-DD.txt.age`, with directory mode
`0700` and ciphertext mode `0600`, both `root:root`. Keep the `age` private
identity on separately controlled, LUKS-encrypted removable media. Verify
decryption through a no-output check, record the ciphertext checksum, and
securely remove all transfer intermediates.
Do not store the share as plaintext in `/home/admin/.lxv`, the repository, a
shell variable retained in history, or an Ansible Vault deployment bundle.
Do not pass a share as a command argument or pre-feed an interactive terminal.

A one-share/one-threshold seal is operationally simple but has no tolerance for
loss of its sole share. Prefer a separately approved multi-custodian threshold
such as 2-of-3 and Vault's PGP-encrypted share output. Keep the initial root
token and unseal shares under different operational controls.

## 5. Reconstruct and re-enroll

With a short-lived administrative token:

```bash
read -rsp "Temporary Vault admin token: " VAULT_TOKEN
echo
export VAULT_TOKEN
luxnix-vault-bootstrap-hub-pki
systemctl restart luxnix-vault-publish-hub-client-ca.service
install -d -m 0700 /root/vault-enrollment
luxnix-vault-enroll-hub-site gc-02.intern /root/vault-enrollment/gc-02
luxnix-vault-enroll-hub-site gc-10.intern /root/vault-enrollment/gc-10
unset VAULT_TOKEN
```

Follow [Vault Hub Machine Enrollment](vault-hub-machine-enrollment.md) for
authenticated delivery, fingerprint verification, atomic installation, and
startup. Replace each site's AppRole IDs, Vault server CA copy, source-node
secret, client certificate, and key. Install matching source-node secrets on
`gs-02` and rerun `lx-annotate-hub-node-provisioning.service`.

Because the internal client CA changed, an existing unexpired client leaf may
still be present on a site. Quarantine it before starting certificate issuance;
expiry alone does not prove that it chains to the new CA. Verify the replacement
certificate against the newly delivered `client-ca.pem` as described in the
enrollment guide.

## 6. Complete and back up

Verify Vault, CA publication, both site authentication chains, managed secret
delivery, and the LX-Annotate transfer path. Confirm old AppRole credentials no
longer authenticate and remove temporary plaintext enrollment directories.

The rebuild is incomplete until an encrypted Raft snapshot backup and restore
drill are scheduled. Keep snapshot encryption keys separate from `gs-02` and
from the new Shamir shares. Test the custody and unseal procedure at least
quarterly, including access by the required threshold of custodians.
