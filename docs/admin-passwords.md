# Admin Password Creation and Rotation

This is the canonical procedure for creating, installing and rotating the LuxNix
`admin` account password. Run commands from the repository root through Devenv.
Replace angle-bracket arguments with the selected host and operator paths.
This guide documents operator actions; creating the guide does not authorize a
production installation or password change.

The workflow is **create → import the password/hash pair → validate → export →
apply → verify**. Local import and file distribution alone do not rotate a live
account. HashiCorp Vault AppRoles, hub node secrets and client certificates have
a separate [enrollment and incident workflow](vault-hub-machine-enrollment.md).

## 1. Select the host and establish recovery

Record the inventory hostname, verified SSH identity/address, repository commit,
`flake.lock` revision and operator. Select one host for each live rotation.
Use a trusted, reviewed durable checkout and control machine; after a breach,
contain access and establish trust in the target before delivering replacements.

For an existing machine, keep an independently verified SSH-key session with
working privilege escalation or a trusted root console open. Do not close it
until acceptance completes. SSH password authentication stays disabled where
configured; do not enable it to test a password change.

Discover the configured hosts and inspect the selected account contract. This
read-only example selects `gc-05`; change `admin_host` to another listed host as
needed. `<host>` is a documentation placeholder, not a flake attribute:

```bash
nix eval --json '.#nixosConfigurations' --apply builtins.attrNames
admin_host=gc-05
nix eval --raw ".#nixosConfigurations.${admin_host}.config.user.admin.name"
nix eval --raw ".#nixosConfigurations.${admin_host}.config.user.admin.passwordFile"
```

The YAML workflow catalog represents these commands as
`nix eval --raw '.#nixosConfigurations.<host>.config.user.admin.name'` and
`nix eval --raw '.#nixosConfigurations.<host>.config.user.admin.passwordFile'`.
Substitute the selected hostname for `<host>` before running those templates.

The supported rotation playbook requires the account name `admin`, the canonical
vault-file hash path and SHA-512 crypt hashes. SOPS, renamed accounts and other
live hash formats require a separately reviewed source-specific migration;
do not bypass the playbook guard. The NixOS activation guard also accepts
protected yescrypt files, but that does not make them supported by this playbook.

For a new host, first add canonical inventory/host YAML, validate Autoconf,
regenerate and review derived configuration using [Getting Started](getting-started.md).
Do not use `--skip-sync` until that host exists in the local vault inventory.

## 2. Create the private password input

Generate a fresh unique password in the operator's approved password manager;
retain it in the protected recovery record. Never reuse another host's password
or a breached password. The importer generates the corresponding login hash;
do not maintain or rotate the hash independently.

Create a private YAML input outside the checkout on operator-owned tmpfs. Its
structure is a top-level `admin_passwords` mapping from exact inventory hostname
to a nonempty string password. Include only the intended host for rotation.
Use a secure editor with swap, backup and session recording disabled, or this
hidden-input snippet from an interactive terminal:

```bash
umask 077
uv run python - <<'PYINPUT'
import getpass
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import warnings
import yaml

runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
info = runtime.lstat()
if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700):
    raise SystemExit("Use an operator-owned mode-0700 runtime directory")
if subprocess.check_output(
    ["findmnt", "-n", "-o", "FSTYPE", "--target", str(runtime)], text=True
).strip() != "tmpfs":
    raise SystemExit("The runtime directory must be on tmpfs")
warnings.simplefilter("error", getpass.GetPassWarning)
with open("/dev/tty") as terminal:
    print("Inventory hostname: ", end="", flush=True)
    host = terminal.readline().strip()
if (not re.fullmatch(r"[a-z0-9-]{1,63}", host)
        or not host[0].isalnum() or not host[-1].isalnum()):
    raise SystemExit("Invalid inventory hostname")
password = getpass.getpass("New admin password: ")
if not password.strip() or password != getpass.getpass("Confirm password: "):
    raise SystemExit("Empty or mismatched password; no file written")
fd, filename = tempfile.mkstemp(prefix="luxnix-admin-", suffix=".yml", dir=runtime)
with os.fdopen(fd, "w") as stream:
    yaml.safe_dump({"admin_passwords": {host: password}}, stream)
print(f"Private input file: {filename}")
PYINPUT
```

Use the printed path as `<admin-passwords-file>` below. The file is mode `0600`;
only its path is printed. Never pass a password through shell arguments,
`--extra-vars`, environment variables, logs or Git. Keep swap encrypted or
disabled. Remove the plaintext input after acceptance and recovery-record
verification; after a failure, retain it only while needed in protected tmpfs.
A process crash can leave private staging files requiring cleanup.

## 3. Import the paired credential

Use the same explicit vault directory, master key and control-host identity on
every invocation. Back up the existing encrypted vault, metadata, host PSKs and
master key under the custodian's protected backup policy before modifying them.
Master keys and input files must be private regular non-symlink files.

Local ciphertext uses the `luxnix-master` identity; host exports use registered
host PSKs. A wrong/missing key fails closed. For an older vault, complete the
[explicit legacy-key migration](vault-setup.md#migrate-legacy-ciphertext-before-running-the-updated-bootstrap)
first. Never create a replacement master key beside existing ciphertext.

For a fresh vault or a newly added inventory host:

```bash
devenv shell vault-bootstrap \
  --vault-dir ~/.lxv --vault-key ~/.lxv.key \
  --local-hostname <control-host> \
  --admin-passwords <admin-passwords-file>
```

For rotation of an existing host already registered in the vault:

```bash
devenv shell vault-bootstrap \
  --vault-dir ~/.lxv --vault-key ~/.lxv.key \
  --local-hostname <control-host> --skip-sync \
  --admin-passwords <admin-passwords-file>
```

Fresh bootstrap generates the master key if absent, syncs the configured generated
inventory, creates/reuses PSKs and updates `conf/ansible.cfg`. `--skip-sync` avoids
inventory/template synchronization but still loads the vault and ensures the
control-host PSK. Neither command above exports or contacts a target.
The input changes only the listed admin pairs; inventory synchronization can
create other baseline secrets. Inspect scope before running it.

The importer stores encrypted plaintext and its encrypted SHA-512 crypt hash
under `secrets/password/local/admin@<host>/`. It writes the pair sequentially.
After any failure, stop distribution, correct the cause and complete a successful
paired import and validation. `scripts/update_secret.py` refuses paired login
credentials and must not be used for admin rotation.

## 4. Validate, then export

```bash
devenv shell validate-admin-passwords \
  --vault-dir ~/.lxv --vault-key ~/.lxv.key \
  --admin-passwords <admin-passwords-file> --vault-id luxnix-master
```

A zero exit code verifies the stored plaintext and hash against every host in
the input. A nonzero result blocks deployment. Export the validated state without
reimporting or regenerating the pair:

```bash
devenv shell vault-bootstrap \
  --vault-dir ~/.lxv --vault-key ~/.lxv.key \
  --local-hostname <control-host> --skip-sync --export
```

Export covers registered clients, not just the host in the password input.
Review the resulting host bundle list. Host-encrypted files are under
`~/.lxv/deploy/<host>/`, with admin targets
`SCRT_local_password_admin_password` and
`SCRT_local_password_admin_password_hash`. Ansible must have the matching PSK
and inventory paths from the generated configuration. Do not print decrypted
exports to inspect them.

Serialize import, validation, export and delivery: the export lock does not
cover other writers or Ansible readers. Missing PSKs and encryption errors fail
the export and retain prior output. Publication uses two renames, not a
crash-atomic transaction. If `.deploy-previous` remains after interruption, stop
and have the custodian reconcile it with `deploy` against the intended revision.
Do not blindly delete the recovery marker or distribute a partial export.

## 5. Apply to an existing machine


Use the dedicated consumer workflow after paired import, validation and export:

```bash
devenv shell check-connectivity <host>
devenv shell rotate-admin-passwords --limit <host> \
  -e admin_rotation_recovery_confirmed=true
```

Before any credential write, the command validates the prepared pair and opens
an interactive prompt on the control machine's terminal:

```text
This password will only be shown once during this run. Store it in a safe place.
Machine: <host>
New admin password: (the validated replacement is displayed here)
Activate new admin password for machine <host>? [y/n]:
```

Store the displayed password in the protected password manager/recovery record,
then type `y` and Enter to activate that exact replacement on the named machine.
Type `n` or press Enter to cancel before password files or the account are changed.
Other answers prompt again without redisplaying the password. A pipe, CI job or
missing controlling terminal cannot approve the operation; there is no automatic
confirmation flag. The earlier local import/export remains prepared after cancellation.

The password is displayed once **per invocation**, directly to the terminal device selected by the wrapper, outside
Ansible stdout, stderr and logs. It remains in the encrypted vault and can be
shown again by a later invocation. Terminal scrollback, session recorders and
screenshots can retain it; use a private, unrecorded terminal. The approved pair
is held as one in-memory snapshot through activation, so later export-file changes
do not substitute a different password after approval.

This prompt protects this rotation workflow. Direct playbook invocation without
the wrapper-provided interactive terminal fails closed.
It does not prevent root changes, general secret deployment or NixOS activation
from changing an account through the other configured password paths.

The `admin_rotation_recovery_confirmed=true` argument records that a separate SSH key session with working privilege
escalation, or a trusted root console, has been verified. Run from the reviewed
durable checkout and with the registered host PSK available to Ansible. Never
pass password values using `--extra-vars`. The playbook accepts one host, checks
its evaluated admin hash path, validates the exported plaintext/hash pair locally,
rejects reusing the current password, requires terminal approval, persists root-owned files,
updates the live account and verifies the resulting shadow hash. Secret-bearing
tasks suppress logs and diffs; SSH host-key checking stays enabled.
The wrapper requires private controller tmpfs for Ansible's temporary plaintext
files and removes its staging on ordinary success or failure. Keep swap encrypted
or disabled; a crashed process can leave private runtime staging requiring cleanup.

This workflow supports the canonical vault-file `admin` account and SHA-512 crypt
hashes generated by the importer. SOPS-backed, renamed or other hash-format
accounts fail with an explicit migration requirement. If any step fails, keep
access contained and rerun with a fresh validated pair; never restore a breached
password. A successful rerun with the already-installed hash is idempotent.
Password rotation does not end existing sessions: terminate compromised
sessions separately from the verified root console/independent account, then
check new login acceptance and old login rejection. Do not terminate the only
active recovery connection. Database and application sessions have separate
owners and are not changed by this account workflow.

## 6. Install on a new machine


Activation no longer manufactures the shared recovery password. Provision a
unique root-owned, mode-`0600` or `0400` admin hash at the evaluated
`user.admin.passwordFile` before first activation, using the documented encrypted
host export and authenticated installer channel. Existing files containing the
retired shared hash are rejected too: rotate those accounts before deploying
the new activation guard. Explicit legacy fallback settings also fail evaluation.

For a fresh installation, use nixos-anywhere's documented
[`--extra-files` staging tree](https://nix-community.github.io/nixos-anywhere/howtos/secrets.html).
Create the tree in a private, operator-owned tmpfs directory and place the
decrypted host-export hash at the relative path matching the evaluated
`user.admin.passwordFile`. Decrypt directly into that protected file without
printing its contents; verify its hash format, root ownership and mode `0600`.
Keep the host-export decryption key outside the staging tree. Add
`--extra-files <staging-root>` to the installation command in the Getting
Started guide only after confirming the exact target and destructive install
scope. The installer copies this tree before first activation. Remove the
decrypted staging tree after acceptance, including after a failed installation.
Verify SSH-key login and independent privilege recovery before closing the
installer session.

For a separate recovery credential, configure the existing password-file option
to a unique, protected runtime file. Do not place a hash or plaintext password in
Nix or YAML. Preserve independent SSH-key access and verify sudo or root-console
recovery before deployment. Missing, malformed or over-permissive files stop
activation before account mutation; they never restore the old shared password.

## 7. Verify and close the rotation

Record each result without password or hash values:

- The playbook verified that the running account adopted the exact exported hash.
- A separate SSH-key login and privilege/console recovery still work.
- The new password succeeds and the retiring password fails on an already-enabled
  password-consuming path. A fresh local console login is suitable; an existing
  authenticated shell or cached sudo authorization is not proof. Keep the
  recovery session open and account for login lockout limits.
- After a breach, compromised sessions are terminated through the independent
  root console/account. Password changes do not revoke SSH keys, sudo timestamps,
  application sessions or database connections; handle affected credentials with
  their owners before lifting containment.
- The protected recovery record and encrypted backup reflect the replacement,
  and temporary plaintext input/installer staging has been removed.

Record host/revision, operator, validation and adoption results, plus timestamps
for containment, rotation and old-credential rejection. Mark unreachable or
unverified hosts pending; repeat the one-host workflow for each affected host.
Do not declare a fleet rotation complete from an export or a single host result.

## Failure and recovery

On any failure, keep access contained and use the independent recovery path.
Correct inventory, permissions, key identity or consumer configuration, then
reimport and validate a fresh pair before retrying delivery. The live playbook
is idempotent when its replacement hash is already installed; it rejects a new
hash that merely reuses the current password.

Do not restore a breached password as rollback. Restore encrypted snapshots only
when their credentials are uncompromised and the custodian has reconciled any
changes already adopted by live accounts. Keep retiring encryption keys while
retained backups depend on them; encryption-key migration is a separate operation.

The source review and remaining controlled acceptance requirements are recorded
in `secrets-management.yml` at the repository root. Local tests do not establish
production login rejection, session termination or measured recovery time.
