# Login and remote storage access

`luxnix.storage.loginAccess` coordinates an already enrolled, passphrase-sealed
local OpenBao store and adopted operator-storage volumes. It does not format
volumes, replace application encryption keys or initialize OpenBao during login.
The shared EndoReg role selects this mode automatically once its storage method
is `local-openbao` and its OpenBao seal is `passphrase`. Direct LUKS passphrase
profiles retain their existing unlock workflow until enrollment and adoption
are complete. There are no gc-09/gc-10 policy exceptions.

## Login and background processing

Both configured admin and enabled client accounts are allowed by default.
A PAM authentication hook captures their password in locked, non-dumpable
memory. The session hook uses it only after successful authentication. SDDM
includes the `login` PAM stack; password-based SSH also supports the hook.
Key-only SSH, automatic login and unlocking a screen without opening a new PAM
session do not provide this trigger. Use the remote command in those cases.
Login remains available for recovery if storage cannot unlock; an error is
reported and the application must not be assumed available.

Each account has its own root-only, scrypt-protected wrapping of the existing
random OpenBao seal key under `/var/lib/openbao-bootstrap/login/`. Neither its
password nor an unencrypted persistent seal key is written there. The helper
stages the verified seal on protected runtime storage, starts OpenBao, mounts
storage and starts the configured guarded services. Existing managed-secret
startup units then deliver application secrets through their existing guards.
This does not create missing application secrets or replace their credentials.

Logout and screen locking leave the application running. Storage stays open
until shutdown or an explicit administrative lock. Application-level encryption
remains independent and enabled. Root and sudo administrators can inspect
unlocked data; this is not protection against a compromised running root account.

## Initial setup and password changes

First complete [OpenBao enrollment and volume adoption](openbao-local.md) with
independent recovery custody, retaining the working LUKS recovery credentials.
Select the shared `local-openbao` profile only after those checks and the existing
pre-switch check pass. Login access cannot bootstrap from a Linux password hash:
the account must actually authenticate with its password.

After deploying the reviewed configuration, an administrator can stage the
existing seal through a private terminal:

```bash
sudo luxnix-storage-access bootstrap
```

Enter the existing OpenBao boot/recovery passphrase at its hidden prompt.
While that authenticated seal is staged, the next successful password login
of each allowed account automatically creates its missing encrypted credential.
Account passwords must satisfy the existing seal-wrapper minimum of 12 bytes.
Thereafter either account can unlock storage after a reboot without entering a
separate OpenBao passphrase. Verify both accounts before relying on this path.
The recovery boot passphrase and its wrapped record remain unchanged.

Password changes do not silently rewrap credentials. After changing an account
password, keep a working recovery path, bootstrap the seal if necessary, then:

```bash
sudo luxnix-storage-access forget --user client-user
```

The next successful password login enrolls the new credential. Until the old
record is removed, it remains decryptable with the old password. Removing a
record does not terminate running services or revoke an already staged seal.
Set `autoEnroll = false` when automatic recreation is not desired. Removing an
account from `users` immediately disallows it after activation; remove its
persisted record as part of account retirement.

## Remote operations

Run from the administrator's private terminal, with the normal pinned SSH host
identity checks. Commands must run through sudo; there is no setuid unlock tool
and no password argument or password environment variable.

```bash
ssh -t admin@172.16.255.110 'sudo luxnix-storage-access status'
ssh -t admin@172.16.255.110 'sudo luxnix-storage-access unlock --user admin'
ssh -t admin@172.16.255.110 'sudo luxnix-storage-access lock'
```

`unlock` prompts for the named account's enrolled login password. Concurrent
login and remote operations are serialized. `lock` removes the startup gate,
stops the declared consumers and their timers/path triggers, unmounts binds
before backing volumes, closes LUKS mappings, stops OpenBao and removes its
runtime seal key and receipt. A busy filesystem or failed stop aborts locking;
there is no forced or lazy unmount. Check status after an error: partially
stopped services do not imply that all volumes are locked. Resolve the remaining
consumer and retry, or explicitly unlock to resume the application.

The application's database and workers stop during an explicit lock. Work in
progress can be interrupted; finish or pause imports before planned locking.
Guarded services cannot automatically reopen storage without a new authorized
unlock. `status` reports the authorization gate, open mappings and staged seal
without printing credentials.

## Secrets visibility

Backing volume roots, including `/var/lib/luxnix-secrets`, are owned by root
with mode `0700`; container files use `0600`. They are marked hidden from desktop
volume browsers. Ordinary accounts cannot browse the backing folder, even after
login unlocks storage. Manual inspection requires sudo. Services retain access
through their declared bind mounts and existing per-secret permissions; root
permissions are not applied recursively to application data or secret files.

## Verification

Run the Python lifecycle tests and the disposable real PAM/OpenBao/LUKS VM:

```bash
python -m pytest -q tests/test_storage_login_access.py
nix build .#checks.x86_64-linux.storage-login-access --no-link
```

A production rollout still needs enrollment/adoption and verification on the
physical host: both account logins, remote lock/unlock, login recovery on failure,
background processing after logout, application decryption, and cold boot.
