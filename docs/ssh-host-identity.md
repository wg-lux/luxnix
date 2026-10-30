# SSH Host Identity

## Server trust and user login are separate

| Key | What it proves | Where its public key belongs |
| --- | --- | --- |
| Server host key, normally `/etc/ssh/ssh_host_ed25519_key.pub` on the destination | You reached the intended machine | LuxNix's `conf/ssh-host-keys/known_hosts` registry and the connecting client's known-hosts trust |
| User login key, for example `~/.ssh/id_ed25519.pub` on the connecting machine | You may log in as the destination account | The destination's authorized keys; LuxNix configures admin access with `services.ssh.authorizedKeys` |

A `SHA256:...` fingerprint identifies a key; it is not the full public key and
cannot be pasted as an authorized-key or known-hosts entry. Never copy a client
private key to the server. Changing `ansible/inventory/hosts.ini` changes the
inventory address, not the destination's login permissions. It also does not
change a direct `ssh user@IP` invocation.

The LuxNix SSH module maps `services.ssh.authorizedKeys` to
`users.users.<admin-name>.openssh.authorizedKeys.keys`. The common role contributes
`luxnix.generic-settings.rootIdED25519`; SSH-access roles can contribute further
keys. Password and keyboard-interactive login are disabled, and root login is
disabled. Inspect the selected host's evaluated configuration rather than
assuming a locally available key is authorized.

## Diagnose an admin login failure

On the connecting machine, inspect the public-key fingerprints and offered keys:

```bash
ssh-keygen -lf ~/.ssh/id_ed25519.pub
ssh-add -l
ssh -v -o ConnectTimeout=10 admin@172.16.255.106
```

Here `gc-06` and `172.16.255.106` are examples; confirm the intended target in
the inventory before running them. The client trace's `loaded pubkey` line only
means a local key was found. Look later for `Offering public key` and
`Server accepts key` to determine what happened during authentication.

| Output | Meaning and next check |
| --- | --- |
| Stalls at `Connecting to ...` or times out | Authentication has not started. Check address, VPN route, firewall and whether SSH is listening. |
| `The authenticity of host ... can't be established` | Server identity is not yet trusted. Verify the host key independently before accepting it. |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | The server key conflicts with trusted identity. Stop and investigate; do not delete trust entries merely to connect. |
| `Permission denied (publickey)` | The server was reached, but user authentication failed. Check account, offered key, effective authorized keys and server logs. Editing `known_hosts` cannot fix this. |

To select an existing client key explicitly:

```bash
ssh -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 admin@172.16.255.106
```

Through a trusted console or an existing working administrative connection, the
destination operator can inspect failures without changing authentication:

```bash
sudo journalctl -u sshd --since '15 minutes ago' --no-pager
sudo sshd -T | grep -E '^(authorizedkeysfile|pubkeyauthentication|allowusers|passwordauthentication) '
```

Account-specific `Match` rules require evaluation for the actual connection
context as well. Compare the sender's full `.pub` key with the effective
authorized-key files; inspect ownership and permissions if the key is present.
Use `sshd -T` to discover file locations rather than assuming that only
`~/.ssh/authorized_keys` is used on NixOS.

For durable authorization, update the owning inventory input or SSH-access role
for the intended host scope, preserve existing recovery keys, regenerate managed
host output when applicable, then follow the evaluation, build and authorized
activation steps in [Getting Started](getting-started.md) and
[Deployment Guide](deployment-guide.md). Do not hand-edit generated host Nix
files. Keep console or an existing session available and verify a fresh login
before closing it. See [Access Management](access-management.md) for recovery.

## Host key registry

Luxnix treats SSH host keys as host identity. The public keys live in:

```text
conf/ssh-host-keys/known_hosts
```

Only public host keys belong in the repository. Private host keys must be kept in
an operator-controlled encrypted backup outside the target host root filesystem.
Do not encrypt that backup only with the host's own SOPS identity, because Luxnix
uses `/etc/ssh/ssh_host_ed25519_key` as the SOPS age identity.

## Verify A Host

Prerequisites: use a trusted console or already authenticated VPN path,
confirm the target hostname and address, and compare against the repository
registry before accepting any changed key. Keep the current known-good host
key and an operator-controlled encrypted backup available.

Collect the current host fingerprint:

`ssh-keyscan` collects candidate public keys; it does not authenticate them.
Compare their fingerprints against a trusted console or an independently
verified existing connection. VPN reachability alone does not authenticate an
SSH server.

```bash
ssh-keyscan -T 5 -t ed25519,rsa gc-05 gc-05.intern 172.16.255.105
ssh gc-05 'sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub'
ssh gc-05 'sudo stat -c "ed25519 mtime=%y birth=%w" /etc/ssh/ssh_host_ed25519_key'
```

Compare the public key with `conf/ssh-host-keys/known_hosts` before accepting a
changed key.

## Rotate A Host Key

1. Freeze rebuild, reinstall, and `disko` work for the host.
2. Verify the new public key over a trusted path, for example console or an
   already trusted VPN path.
3. Update `conf/ssh-host-keys/known_hosts` for every hostname and VPN IP alias.
4. Rekey SOPS secrets for the host if the ed25519 host key changed.
5. Rebuild the host.
6. Only after verification, remove stale client entries for the affected names
   and add the matching public host-key lines from the verified registry:

```bash
for name in gc-05 gc-05.intern 172.16.255.105; do
  ssh-keygen -R "$name"
done
```

Use an editor to copy the exact verified registry lines into `~/.ssh/known_hosts`,
preserving unrelated entries. Do not append unverified `ssh-keyscan` output.

Validate the rotation from a fresh connection: confirm the fingerprint of the
new key, verify the expected host identity and SSH service, and check that
SOPS secrets decrypt with the rekeyed identity where applicable. If the new
key is wrong or the host becomes unreachable, stop accepting connections,
restore the backed-up private/public host keys with root ownership and the
modes below, restart `sshd`, and remove/re-add the client entry only after the
fingerprint matches the trusted backup. If the host configuration itself
caused the outage, boot or switch the previous NixOS generation before
repeating the rotation.

## Backup Private Host Keys

After a trusted install, back up the private host keys to an encrypted operator
store such as:

```text
/home/admin/.lxv/host-ssh-keys/<host>/
```

The minimum files to preserve are:

```text
/etc/ssh/ssh_host_ed25519_key
/etc/ssh/ssh_host_ed25519_key.pub
/etc/ssh/ssh_host_rsa_key
/etc/ssh/ssh_host_rsa_key.pub
```

Keep permissions root-only on restore:

```bash
sudo chown root:root /etc/ssh/ssh_host_*_key*
sudo chmod 0600 /etc/ssh/ssh_host_*_key
sudo chmod 0644 /etc/ssh/ssh_host_*_key.pub
sudo systemctl restart sshd
```
