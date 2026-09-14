# HashiCorp Vault Owner Operations

This guide covers routine custody, status, seal, and unseal operations for the
HashiCorp Vault service on `gs-02`. It does not cover the independent LuxNix
Ansible Vault (`~/.lxv` and `~/.lxv.key`). Never use one system's recovery
material as a backup for the other.

## Custody model

The unseal share is a long-lived recovery secret. Store only an encrypted copy
on an online machine. Keep the corresponding decryption identity offline on a
LUKS-encrypted removable volume, with a separately controlled offline backup.

The project convention is:

| Material | Location | Required protection |
| --- | --- | --- |
| Encrypted unseal share | `/root/vault-custody/gs-02-unseal-share-YYYY-MM-DD.txt.age` on `gc-06` | `root:root`, mode `0600` |
| Ciphertext directory | `/root/vault-custody` on `gc-06` | `root:root`, mode `0700` |
| `age` private identity | Approved removable custody volume | LUKS encrypted; absent from `gc-06` except during a ceremony |

Do not store a plaintext share in the repository, Ansible Vault deployment
tree, shell history, terminal scrollback, clipboard, chat, or a regular file.
Do not keep the decryption identity beside the ciphertext.

The current one-share/one-threshold arrangement is a single point of failure.
At the next approved rekey ceremony, prefer multiple separately controlled
shares and a threshold that tolerates loss of one custodian (for example,
2-of-3). Use Vault's PGP-encrypted share output where practical.

## Check status

Use a trusted console or an SSH connection whose host key is already verified:

```bash
sudo -i
export VAULT_ADDR=https://172.16.255.22:8200
export VAULT_CACERT=/var/lib/luxnix-vault-pki/ca.crt
export VAULT_TLS_SERVER_NAME=vault.endo-reg.net
vault status
```

`172.16.255.22` is the Vault listener on the AGLNet VPN. The separate TLS
server name keeps certificate verification bound to `vault.endo-reg.net` and
avoids public-DNS routing from `gs-02`. Do not use the public address
`178.104.136.182` for local operator commands.

Exit status `2` means Vault is sealed; it is not a command failure. Continue
only if the certificate validates and Vault reports `Initialized true`.

## Unseal after restart

Mount the custody volume only for the ceremony. Decrypt the share into process
memory and enter it at Vault's hidden prompt. The final command deliberately
has no share argument:

```bash
vault operator unseal
vault status
```

Never run `vault operator unseal <share>`: command arguments can be retained in
history, process inspection, audit tooling, or transcripts. Never automate an
interactive prompt by pre-feeding a pseudo-terminal.

Required result: `Initialized true` and `Sealed false`. Clear temporary process
state, close the no-logging terminal, and unmount and remove the custody volume.
Clients never receive the unseal share.

## Seal for an approved operation

Sealing interrupts every Vault-dependent authentication, certificate-renewal,
managed-secret, and hub-transfer workflow. Confirm the outage and that an
authorized custodian can unseal before proceeding. Sealing requires an
appropriately privileged, short-lived token:

```bash
read -rsp 'Temporary administrative Vault token: ' VAULT_TOKEN
echo
export VAULT_TOKEN
vault operator seal
unset VAULT_TOKEN
vault status || true
```

Do not use or retain the initial root token for routine operations.

## Verify service recovery

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
for host in gc-{01..10}; do
  luxnix-vault-enroll-hub-site \
    "$host.intern" "/root/vault-enrollment/$host"
done
After unsealing, verify the service chain without printing credentials:

```bash
systemctl is-active vault.service \
  luxnix-vault-publish-hub-client-ca.service
vault status
```

Then verify enrolled clients with `luxnix-vault-enrollment-status` and the
service checks in [Vault Hub Machine Enrollment](vault-hub-machine-enrollment.md).

```text
/etc/secrets/vault/hub-pki/gc-01-source-node-secret
...
/etc/secrets/vault/hub-pki/gc-10-source-node-secret
```

Stop. Do not initialize Vault over existing storage. Search approved custodians
and backup inventories, then follow the gated
[Vault Server Rebuild](vault-server-rebuild.md) procedure only after accepting
the loss of the old barrier-encrypted data and dependent credentials.

## Non-secret confirmations

- Vault is unsealed.
- Hub PKI bootstrap completed.
- Client-CA publication is active.
- The safe AppRole implementation is deployed on every GC site.
- Old Secret IDs were revoked and replacement bundles were delivered.
- Receiver-side node-secret files were installed.
