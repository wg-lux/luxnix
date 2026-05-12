# SSH Host Identity

Luxnix treats SSH host keys as host identity. The public keys live in:

```text
conf/ssh-host-keys/known_hosts
```

Only public host keys belong in the repository. Private host keys must be kept in
an operator-controlled encrypted backup outside the target host root filesystem.
Do not encrypt that backup only with the host's own SOPS identity, because Luxnix
uses `/etc/ssh/ssh_host_ed25519_key` as the SOPS age identity.

## Verify A Host

Collect the current host fingerprint:

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
6. Remove stale client entries and re-add from the registry:

```bash
for name in gc-05 gc-05.intern 172.16.255.105; do
  ssh-keygen -R "$name"
done
ssh-keyscan -T 5 -t ed25519,rsa gc-05 gc-05.intern 172.16.255.105 >> ~/.ssh/known_hosts
```

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
