
# TPM release client

`luxnix.tpmReleaseClient.enable` installs `luxnix-tpm-release`, the client side
of central volume release by gs-02 (acceptance criteria ENC-05 and ENC-06 in
`boot-encryption-acceptance.yml`). It is disabled by default and is not yet
wired into the unlock path of `luxnix.storage.operatorUnlocked`. No host
changes behavior until a later, separately reviewed change enables it through
inventory.

## Device identity

The TLS client key is generated inside the host TPM as a child of the TCG
storage root key at persistent handle `0x81000001`, the same handle that
`systemd-cryptenroll` uses. The key is ECC P-256 with the attributes
`fixedtpm|fixedparent|sensitivedataorigin|userwithauth|sign|noda`: it cannot be
exported or duplicated and it can only sign. The key file
(`/var/lib/luxnix-tpm-identity/device.tss2.pem`) is a TSS2 blob wrapped by
that TPM. A copy of the unencrypted root disk therefore does not carry a usable
identity; loading the blob on another TPM fails.

The key, certificate and pinned release CA live on the root filesystem, outside
every operator-unlocked volume and bind, because they are needed before any
volume opens (ENC-07). The module rejects paths below those mounts.

```bash
# Once per host, as root. --create-srk persists the TCG SRK only if absent.
sudo luxnix-tpm-release identity-create \
  --key /var/lib/luxnix-tpm-identity/device.tss2.pem \
  --csr /var/lib/luxnix-tpm-identity/device.csr \
  --name "$(hostname)" --create-srk

# After enrollment has issued device.pem for the CSR:
sudo luxnix-tpm-release identity-check \
  --key /var/lib/luxnix-tpm-identity/device.tss2.pem \
  --cert /var/lib/luxnix-tpm-identity/device.pem --name "$(hostname)"
```

`identity-create` refuses to overwrite an existing key or CSR. Regenerating an
enrolled identity is a re-enrollment and must go through the enrollment
workflow. `identity-check` verifies the TSS2 attributes, the certificate name,
and possession by signing a random challenge in this TPM and verifying it with
the certificate's public key.

The empty key authorization is deliberate for unattended boot. Any root process
on the running host can use the key; this does not protect against a
compromised running system (see ENC-09 for integrity).

A TPM clear, a TPM replacement or a mainboard swap destroys the identity. The
host then needs re-enrollment, and its volumes open through the independent
LUKS recovery path (ENC-18).

## Release request

```bash
luxnix-tpm-release fetch --url https://<gs-02-release-listener> \
  --ca /var/lib/luxnix-tpm-identity/release-ca.pem \
  --cert /var/lib/luxnix-tpm-identity/device.pem \
  --key /var/lib/luxnix-tpm-identity/device.tss2.pem \
  --name "$(hostname)" --volume luxnix-secrets
```

The client logs in with OpenBao certificate authentication
(`auth/cert/login`, role = host name) over mTLS using the TPM key, then reads
`<mount>/data/<host>/<volume>` once with the returned single-use token. Only the
value of the `key` field is written to stdout, without a trailing newline, so it
can be piped into `cryptsetup --key-file=-`. Nothing is cached. Tokens and
request bodies travel to curl on stdin and never appear in process arguments.
The release CA is pinned; system trust stores and proxies are not used.

| Exit | Reason | Meaning |
|------|--------|---------|
| 2 | `release-config`, `release-malformed`, `release-unexpected` | Invalid configuration or response |
| 3 | `release-unreachable` | gs-02 release listener not reachable |
| 4 | `release-denied`, `release-tls-rejected` | Identity, role, policy or pinned CA rejected |
| 5 | `release-sealed` | Release service sealed or unavailable |
| 6 | `release-not-found` | No release record for this host and volume |
| 7 | `identity-*`, `srk-*`, `tpm-tool-failed` | TPM identity missing, foreign or malformed |

Error messages carry only the reason and the stage, never payloads.

## Verification and limits

`tests/test_tpm_release.py` runs the client against two software TPMs (swtpm)
and a synthetic mTLS release server that mirrors the OpenBao VM test
(`tests/nixtest/openbao_release.py`):

```bash
uv run pytest -q tests/test_tpm_release.py
```

It covers SRK handling, sign-only non-exportable keys, refusal to regenerate,
rejection on a foreign TPM, plaintext keys and mismatched certificates,
single-use release, and every exit class. A software TPM proves the protocol
and key handling only. It is no evidence for physical hosts (ENC-25), and the
client has not yet been run against the real OpenBao listener.

Still open before any host is enabled:

- Enrollment command that signs the CSR, creates the per-host cert role, policy
  and release records on gs-02, and installs `device.pem` and the pinned CA
  (ENC-22).
- Integration into the operator-unlocked unlock path with the 90-second bound
  and the per-volume LUKS keyslot (ENC-05, ENC-13).
- Reachability of gs-02 before the volumes open, including the VPN path (ENC-07).
- Root and Nix store integrity (ENC-09).
- Hardware tests per hardware class (ENC-11, ENC-25).
