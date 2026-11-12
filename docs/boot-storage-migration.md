# Boot LUKS migration and recovery

New machines start with the [setup quickstart](boot-storage-quickstart.md). This
reference covers encrypting an existing installation in place and recovering
retained storage. The
[current contract](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml)
holds the requirements; historical OpenBao/TPM acceptance and retired installer
details are in the [versioned archive](https://github.com/wg-lux/luxnix/blob/39eeabdbc52af4129eafb76bfa9e8d84757ade92/docs/boot-storage-migration.md).
Live hosts are accepted by their own physical evidence.

## Shared encryption contract

Root uses LUKS2 with one operator passphrase and unlocks without a network key
service. Secondary keys live on the encrypted root, outside EFI, the initrd and
the Nix store. Homes, Nix, logs and secrets sit on encrypted storage; MD arrays
assemble below LUKS and every Btrfs member has encrypted backing. Swap is encrypted
or disabled. Protected writers start only on the right storage, and boot services
keep existing storage and keys as they are.

| Role | Mapping |
| --- | --- |
| Root | `cryptroot` |
| Application volume | `luxnix-app-storage` |
| Retained secrets volume | `luxnix-secrets` |
| Encrypted swap | `cryptswap` |
| Other data/members | `luxnix-data-<mount-path>`, optionally `-member-N` |

LUKS, login, wallet and application passwords are independent. Storage changes
keep existing application keys, salts and account hashes; accounts change through
[explicit rotation](admin-passwords.md#explicit-replacement-and-activation-safety).
SDDM shows the account chooser, with auto-login disabled.

### Splash unlock and generation recovery

The initrd unlocks the LUKS2 header on the configured root partition and boots
only from it. A host whose disk is still plaintext selects `legacy-containers`;
the target-host preflight admits only generations that match the physical disk
(see [boot storage recovery](boot-storage-recovery.md)). The plaintext bridge
`plaintextRootBridge` exists for disposable test machines only.

Plymouth uses the graphical `bgrt` theme (firmware logo, spinner and password
field) and waits for the passphrase without a limit. Without a usable
framebuffer it falls back to its text prompt. Keep console access and a matching generation. After a failure, compare
`/run/current-system`, `/run/booted-system`, the system profile and the bootloader
default separately. Rollback selects software only; disk conversion, keys and
application data stay as they are.

### Explicit password verification

On an encrypted host, run the helpers from the reviewed candidate in a private
terminal (replace `./result` with its path):

```sh
sudo ./result/sw/bin/luxnix-setup-root-encryption --setup-password
sudo ./result/sw/bin/luxnix-verify-boot-storage
```

They diagnose and verify, and record a private host-, UUID- and header-bound
receipt (never the password). `sudo luxnix-setup-boot-password --change` adds a
password after verifying an existing one and backing up the header, keeping all
slots. Cold boot confirms secondary unlock.

## Guided operator workflow

`devenv shell luxnix migrate` preserves and encrypts the existing machine. It reads
`autoconf/config.yml`; `--host`, `--config` and `--device` select reviewed
alternatives. `devenv shell luxnix status` shows progress without changing state.
`devenv shell luxnix storage <action>` and `devenv shell boot-storage-setup` expose
the administrator interface.

### Selecting a host for migration

A host whose running root is already LUKS2 and that has no migration plan has
nothing to convert: `luxnix migrate` stops and names `luxnix inspect <host>`.

`luxnix migrate` plans a host only when all of the following hold. Otherwise it
stops before planning, changes nothing, and lists every missing step at once, in
the order to do them.

1. **The inventory selects `boot-luks`.** Set
   `storage.operatorUnlocked.layout: '"boot-luks"'` under `host_luxnix` in
   `ansible/inventory/host_vars/<host>.yml`, then run
   `devenv tasks run autoconf:check` and `devenv tasks run autoconf:generate`.
   From then until conversion finishes, normal rebuilds of that host are refused
   with `root-not-luks`, so deploy unrelated changes first.
2. **`boot_storage.hosts.<host>` exists in `autoconf/config.yml`,** with facts read
   on the host itself, never copied from `disks.nix`:

   ```yaml
   boot_storage:
     hosts:
       <host>:
         hardware_uuid: <sudo cat /sys/class/dmi/id/product_uuid>
         root_encryption: luks2
         installation: in-place
         source_retention: in-place
         disks:
           - path: /dev/disk/by-id/<disk>
             serial: <serial>
             size_bytes: <bytes>
   ```

   On the target, `ls -l /dev/disk/by-id/` names the disks and
   `lsblk -bdno SERIAL,SIZE /dev/disk/by-id/<disk>` prints each serial and size.
   List **every** disk the host's `disks.nix` declares, system and data disks
   alike, but no external backup disk.
3. **The evaluated layout is convertible:** a Btrfs root plus, optionally,
   independent Btrfs data partitions. MD arrays, multi-member Btrfs and other
   filesystems stop planning; declare each data disk as one Btrfs partition, or
   keep the host on `legacy-containers`.
4. **The host evaluates without failed assertions.**

Then follow the [two-machine migration](migration-environment.md#two-machines-the-standard-setup).

### Configuration and recovery media

Migration requires `root_encryption: luks2`, `installation: in-place` and
`source_retention: in-place`. `boot_storage.hosts.<host>` supplies the hardware UUID
and each disk's exact `path`, `serial` and `size_bytes`; `paths.nix_output` names
the clean release checkout. State lives in `boot_storage.state_root`, normally
`/recovery/luxnix-state/<host>`.

Media preparation picks an existing removable ext4 or Btrfs filesystem apart
from the system and target disks, checks its space and mounts it at `/recovery`.
Use `--device` to choose among several. This drive holds the journal, not a data
backup; credentials go into separate encrypted custody.

Planning pins the revision, lockfile, closure and hardware, and copies the plan's
source to `/recovery/luxnix-state/sources/<revision>` for the RAM environment.
State belongs to the planning operator and stays private; root in the RAM
environment uses it and hands new files back. Conversion starts with targets
unmounted, swap off and no conflicting mappings.

### Replacing a saved plan

Status, next-step inspection, verification and previews only read. Planning or the
guide replaces an outdated plan that has **not started**, keeping the previous one
as `<state>.superseded-<id>`. A plan has not started while its install is pending
and its provisioning journal is absent or `planned`; check `progress.json` and
`provision.json` if unsure. Started plans continue through
[recovery review](#interrupted-setup). A replacement collects fresh preflight and
recovery evidence; keep plan revisions, receipts and journals unedited.

### In-place root encryption

The converter handles the plaintext Btrfs root and independent Btrfs data
partitions; MD arrays, multi-member Btrfs and other filesystems are not converted
(see [selecting a host](#selecting-a-host-for-migration)). In the
[RAM migration environment](migration-environment.md), started from the controller
as the [two-machine standard](migration-environment.md#two-machines-the-standard-setup), `luxnix-migration run
--apply` runs the plan's own source, asks for typed `ENCRYPT IN PLACE` approval and
the passphrases, checks for mains power, moves the boot default to the migration
entry, and then:

1. Tests the container credentials and checks that their data fits on root.
2. Shrinks Btrfs by 32 MiB and runs `cryptsetup reencrypt --encrypt`.
3. Verifies the filesystem UUID and Btrfs consistency, then mounts the encrypted root.
4. Erases the obsolete plaintext swap signature, or reports what to complete by hand.
5. Copies each container's contents onto the encrypted root, compares them, and
   publishes the result; earlier data at those paths stays as
   `<path>.pre-consolidation`.
6. Records the password check and saves a LUKS header backup in
   `header-after-conversion-*/luks.header` beside the state. Copy it into encrypted
   custody and protect it like the passphrase: with a passphrase valid now it opens
   the disk, even after that passphrase is removed.
7. Prepares access and installs the system, in the same session.
8. Clears the boot default override so `loader.conf` selects the installed
   encrypted generation, and verifies it boots the planned closure. Until that is
   proven, the install stays open and reboots return to the migration environment.

The boot default always matches the disk: the old generation before conversion,
the migration environment during it, and the verified encrypted generation after.
The recovery review authorizes starting; once the disk changes, it stays valid until
installation. The prepared review is taken fresh in the same session. The planned
closure may come from the host's own store, mounted at `/mnt`, where it must be
registered.

Choose a conversion passphrase of letters a-x, digits and spaces, which type the
same on every keyboard layout, and keep it independently. An interruption resumes
from the LUKS2 header with the same journal. Containers stay until acceptance;
afterwards `devenv shell luxnix retire-containers` previews their removal, and
`--apply` deletes them after typed approval, keeping their vault recovery records.

### Prepared review in the RAM environment

Run these after **Root encryption finished** and **Access is prepared**, before
installation. If the guide is asking for notes, submit an empty description to
pause first; run commands at the RAM root shell, then return to the guide. Keep
power connected and stay in RAM until installation confirms the new boot default.
These checks work at the laptop's physical console; SSH is optional.

Set the host and pinned source from the saved plan, not the RAM image's version:

```sh
export LX_MIGRATION_HOST="$(python3 -c 'import json; print(json.load(open("/etc/luxnix/migration.json"))["host"])')"
export LX_MIGRATION_STATE="/recovery/luxnix-state/$LX_MIGRATION_HOST"
export PYTHONPATH="$(python3 -c 'import json,os; from pathlib import Path; s=Path(os.environ["LX_MIGRATION_STATE"]); print(s.parent/"sources"/json.loads((s/"plan.json").read_text())["source"]["revision"])')"
```

**Boot artifacts, receipt and target layout.** This read-only check uses the
planned closure, validates its registration, mounts, administrator credentials,
secondary keys, disk identity, LUKS state, kernel/initrd space and password receipt.
Reading the contract inside `/mnt` resolves the target's absolute store symlinks;
a plain `cat /mnt/nix/store/.../etc/...` can follow them into the RAM store.

```sh
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path
from lx_administration.storage import boot_migration as m, root_guard as g

state = Path(os.environ['LX_MIGRATION_STATE'])
with m.locked_state(state):
    plan = m.load_plan(state)
    m.verify_source(plan, state)
    journal = json.loads((state / 'provision.json').read_text())
    if journal['phase'] != 'complete':
        raise SystemExit('STOP: conversion is not complete')
    m.verify_target(plan, m.probe_disks(plan))
    m.require_closure(plan, Path('/mnt'))
    system = plan['config']['closure']
    contract = json.loads(subprocess.check_output([
        'chroot', '/mnt', system + '/sw/bin/cat',
        system + '/etc/luxnix/root-storage.json'], text=True))
    seen = g.observe(contract, root=Path('/mnt'), system=system)
    findings = g.assess(contract, seen, action='boot', system=system,
                        first_install=True, require_receipt=True)
    if findings:
        raise SystemExit('\n'.join(f'{f.code}: {f.message}' for f in findings))
    print('Layout:', contract['layout'], 'bootloader:', contract['bootloader']['kind'])
    print('Initrd:', contract['initrd'], 'receipt:', seen['receipt'])
    layout = plan['config']['in_place']
    print('Declared containers:', len(layout['containers']))
    for volume in layout['containers']:
        if not Path('/mnt' + volume['container']).is_file():
            raise SystemExit('STOP: retained container is missing: ' + volume['name'])
    for target in layout['binds']:
        marker = Path('/mnt/var/lib/luxnix-in-place') / target.strip('/').replace('/', '__')
        if not Path('/mnt' + target).is_dir() or not marker.is_file():
            raise SystemExit('STOP: consolidation evidence is missing: ' + target)
        print('Consolidated target to inspect:', '/mnt' + target)
    print('PASS: planned closure, encrypted mounts, access, receipt and consolidation evidence')
PY
```

Then compare the mount graph:

```sh
lsblk -o NAME,TYPE,FSTYPE,SIZE,MOUNTPOINTS
findmnt -R /mnt
swapon --show
```

Require exit status zero and no guard findings. For the manual-passphrase layout,
the contract must select `boot-luks`, `systemd-boot` (or the reviewed Secure Boot
loader), `unlocks_root: True`, and `plaintext_bridge: False`. Root and its declared
Btrfs subvolumes must use `cryptroot`; `/mnt/boot` must be the selected ESP. Swap
must remain inactive (`swapon --show` prints no devices). The receipt must match
the current LUKS UUID and header, not merely exist. This review checks planned
artifacts; the new boot entry and physical cold boot are verified after install.

**Container data.** A complete conversion includes the converter's checksum
comparison. For each reported target, inspect the expected directories on the
encrypted root and retain the original container. If the plan declares zero
containers, record that fact. Where containers were explicitly discarded, cite
that operator decision; do not claim that their contents were copied or retained.

**Independent recovery credentials.** At the private RAM terminal, retrieve the
credential from its independent custody and test it without closing `cryptroot`:

```sh
LX_MIGRATION_ROOT_DEVICE="$(python3 -c 'import json,os; print(json.load(open(os.environ["LX_MIGRATION_STATE"]+"/plan.json"))["config"]["in_place"]["root_device"])')"
cryptsetup open --type luks2 --test-passphrase "$LX_MIGRATION_ROOT_DEVICE"
```

Require exit status zero. Repeat for every separately enrolled recovery credential
and declared secondary volume. A conversion password and its backup can be the
same credential; do not claim an additional recovery slot unless one was enrolled
and independently tested. Keep credentials out of arguments, notes and logs. Copy
the saved `header-after-conversion-*/luks.header` into independent encrypted
custody; an external plaintext drive alone is not encrypted custody.

**Record the four assessments.** In the guide's dated description, state what you
actually tested for `boot_artifacts_reviewed`, `target_layout_reviewed`,
`recovery_slots_tested` and `container_data_consolidated`. Include exit results,
the reviewed plan/closure, custody location and any authorized container discard;
no passwords, key contents or patient data. Then confirm only performed checks.
To return to the guide:

```sh
luxnix-migration run --apply
```

Alternatively, write private dated notes and run the explicit review:

```sh
umask 077
cat > "$LX_MIGRATION_STATE/prepared-notes.txt"  # type actual results; finish with Ctrl-D
luxnix-migration review --assessor "$(id -un)" --report "$LX_MIGRATION_STATE/prepared-notes.txt"
luxnix-migration advance                    # preview the next step
luxnix-migration advance --apply            # installation still asks for typed approval
```

If the notes were recorded by root on behalf of another operator, name that
operator as assessor. Stop on failed checks. In particular, a missing-contract
error from the pinned installer's verifier must be resolved before installation,
even if reading the contract via `chroot` succeeds. Do not replace a started plan,
edit its source copy or mark a failed check verified to get past the error.
The corrected verifier resolves both the closure's `etc` link and the contract
file's store link inside the target root; boot-default handover uses the same
resolver. An older pinned plan needs a reviewed runtime repair with recorded
original/replacement function hashes, preserving its immutable source and checks.

### Legacy mount overrides

Before installing boot LUKS, retire host-local container mounts that would shadow
the directories now protected by encrypted root. The install preflight rejects
matching `.mount` files under `/etc/systemd/system.control`, together with legacy
`90-luxnix-secret-storage.conf` and `91-luxnix-app-storage.conf` drop-ins. They can
otherwise keep PostgreSQL and LX-Annotate waiting for deleted container devices
after an apparently successful encrypted boot.

Review each reported definition's `What`, `Where` and dependencies. Stop its
affected writers and ensure the old mounts are inactive. Back up only the
matching files on verified encrypted storage, preserve their relative paths,
and retire those originals; keep unrelated units. In the installed system,
`systemctl show <unit> -p FragmentPath -p DropInPaths` identifies loaded overrides.
Reload systemd after the change and start the affected services; confirm the
encrypted-storage checks pass. Never remove the whole `system.control` directory
or disable the storage guards. Legacy-container hosts still need their mounts.

### Recovery and secret preflight

Before asking about the backup, the guide updates one encrypted backup of the host
on the recovery drive, `luxnix-backup-<host>.luks`:

1. A LUKS2 container opened with a random key kept in encrypted custody
   (`<custody>/host-backup-<host>.key`); it grows when the host's data grows.
2. A consistent capture through `snapshot.py`: declared writers stop briefly,
   inner filesystems freeze, read-only snapshots are taken, services restart.
3. `rsync` copies only what changed and removes what was deleted, then a
   `--checksum` comparison verifies every file against the snapshot.
4. Only the newest capture snapshots stay on the host.

New keys use the operator-owned custody root even when older host folders belong
to root. Existing `<custody>/<host>/host-backup.key` credentials are reused. A
missing key for an existing container, conflicting keys or inaccessible storage
stops the backup without generating a replacement or changing ownership.

The guide offers this backup first, recorded as `copy-verified`; another tested
backup can be named instead. A verified copy is a strong start, and a tested
restore remains the proof.

Before conversion, make and test a consistent data backup. Keep LUKS headers,
original application master keys, historical keys and salts, and account
credentials on independent encrypted media. Inventory nested mounts and database
paths, stop writers before dumps or filesystem capture, and prove recovery by
restoring to an isolated encrypted target, querying PostgreSQL and decrypting old
media.

The guide records each backup outcome as `copy-verified` (the automatic backup),
`restore-tested` (operator-reported) or, by a named decision confirmed with
`ACKNOWLEDGED`, as `risk-accepted`. Custody and
a passing preflight cover credentials; the data backup is its own evidence.

The guide prepares or opens custody, copies only missing credentials and verifies
reopening. For custom custody:

```sh
devenv shell luxnix storage preflight --custody <private-encrypted-directory>
```

A controller holding `~/.lxv` also passes `--vault-key-custody <key-copy>` on a
different physical disk; that key must decrypt the copied vault on its own. Custody
is private, encrypted and independent of every target disk. Close and reopen it to
prove the recovery credential, and keep an existing custody file as it is.

Preflight derives the required credentials from the evaluated host: admin and
client hashes, application keys and every salt generation, recipient keys,
OpenVPN/SOPS identities and keys of volumes outside the selected disks. It tests
the admin password privately, compares custody copies under
`<custody>/<host>/secrets/<original-path>` (vault copies under
`<custody>/controller/.lxv`) and authenticates controller vault recovery. Unlock
source containers first; recovery uses the original keys.

The receipt is bound to the plan and valid for 24 hours. [Credential
backup](credential-backup.md) adds authenticated archives; Vault/OpenBao server
data follows [Vault Server Rebuild](vault-server-rebuild.md). Keep passwords,
hashes and key bytes out of notes and logs.

### Evidence and advanced interface

`next` names the required checks, and `review --assessor <name> --report
<private-notes>` records the ones performed. `devenv shell boot-storage-migration`
offers `plan`, `status`, `attest`, `prepare-access`, `check` and `install` for
reviewed automation.

Stages are `recovery`, `prepared` and the physical `acceptance`. Evidence holds
exactly `schema_version: 1`, `plan_id`, `stage`, `checks` and private absolute
`artifacts`, bound to the plan by hash. Reviews before installation are valid for
24 hours; missing evidence pauses the work.

From trusted media, `check --stage provision` validates prerequisites. After
conversion, `prepare-access` keeps or restores the admin hash and can create the
dedicated initrd SSH identity; then record the prepared review and pass
`check --stage install`. The install step verifies hardware, mounts, keys and
access before and after `nixos-install`, under a machine-wide lock. Signed first
installation follows the [signing workflow](secure-boot.md).

### Interrupted setup

Keep `provision.json`, `progress.json`, the pinned artifacts and the backups; the
journal records execution and is separate from the backup. Inspect the hardware,
mount the complete encrypted layout from trusted media, then preview and accept:

```sh
luxnix-migration recover --assessor <admin>
luxnix-migration recover --assessor <admin> --apply
```

Recovery rechecks identities, filesystems and evidence and asks for exact
confirmation; it proceeds only on a fully verified layout. An interrupted
installation needs an `install-recovery` review, then
`boot-storage-migration install --retry-interrupted`, with the journal kept intact.
Fresh-install journals use the path in the [quickstart](boot-storage-quickstart.md).

### Remote SSH root unlock

A root-encrypted host that reboots without remote unlock stays unreachable until
someone types the passphrase at its console. `sudo luxnix-operator-storage start`
does not change that: it needs a booted system. Only the initrd SSH endpoint
below unlocks root remotely, and it is opt-in per host.

`sudo luxnix-operator-storage start` works in a normal SSH session on either
layout: legacy hosts open their existing containers; boot-LUKS hosts verify the
already unlocked root, open secondary mappings with keys on encrypted root,
mount their filesystems, verify storage and start the configured guarded
consumers. It does not encrypt, decrypt or re-open the mounted root.

Before root unlock, the normal system, its SSH server and its OpenVPN client
have not started. Use the dedicated **initrd SSH endpoint** to enter the root
passphrase, then reconnect to normal SSH after boot. The inventory's
`172.16.255.x` OpenVPN addresses are not an early-boot management network.
Use `ssh -tt admin@<host> 'sudo luxnix-operator-storage start'` after boot;
use `ssh -tt -p 2222 root@<management-address>` while root is locked. The
initrd connection uses its dedicated operator key and pinned host key; it cannot
run sudo or arbitrary shell commands. Entering the passphrase unlocks root and
allows boot to continue without removing encryption.

Every host needs an independently reachable wired management network, verified
NIC drivers, dedicated operator keys, an allowed source address/CIDR and a pinned
initrd host identity. Fleet-wide support does not imply these host-specific inputs
are configured or physically tested. Do not enable an incomplete configuration.


Opt in through the host YAML and regenerate: set
`luxnix.storage.operatorUnlocked.remoteUnlock` with the interface and NIC modules,
a static CIDR address, an optional gateway, management `allowedSources` and
dedicated Ed25519 `authorizedKeys`. Port 2222 offers interactive unlock only; the
console works as well. `prepare-access` creates the host identity once and prints
its public key. Pin it through the installer channel, then connect with
`ssh -tt -p 2222` and strict host-key checking. Test the real management network.

#### Physical acceptance before relying on SSH unlock

The staged test sequence is recorded in [boot-storage.yml](https://github.com/wg-lux/luxnix/blob/main/boot-storage.yml).
Start with gc-02 and gc-09, one at a time, and keep the other operator or jump
host running. Keep hardware observations in the ignored private directory
`cmdb/boot-access-checks/`; never put passwords or local host facts into this guide.

First compare the running, booted and persistent system closures with the default
boot entry and inspect one-shot overrides. Inspect the **installed initrd**, not
just the inventory: a normal SSH server or an installed operator command does
not prove that early-boot SSH exists. Confirm normal SSH from the intended
operator as well; otherwise a successful disk unlock can still leave remote
administration inaccessible.

In a private terminal on each host, run `sudo luxnix-verify-boot-storage`. Resolve
the backing device of the **mounted** `cryptroot`, then test its existing disk
passphrase with `sudo cryptsetup open --type luks2 --test-passphrase <device>`.
This tests a keyslot without opening another mapping or modifying credentials.
Do not use a device copied from another host or a historical runbook. Passwords
stay in the terminal; report only the exit status. A missing or inaccessible
receipt is an incomplete observation, not proof that a passphrase was verified.

Before changing any boot entry, require a reserved management address, the exact
wired interface and its drivers, dedicated operator keys and a pinned initrd
host identity. Prove management LAN reachability separately from the VPN. Normal
SSH and initrd SSH can have different listeners and access rules. If using USB
Ethernet, keep its physical port fixed and verify its adapter and USB-controller
drivers; prefer the built-in wired port when possible.

Only after those checks and a successful build of the exact reviewed candidate
should boot staging and an attended reboot be approved. Keep an operator at the
console with the verified disk passphrase, a working keyboard/display and the
previous compatible entry. Unlock through strictly pinned initrd SSH, then
reconnect normally and verify the actual booted closure, encrypted mounts,
administrator access and guarded services. A VM pass or a passphrase test alone
never establishes physical reboot acceptance.

#### Enabling it on an already encrypted host

`prepare-access` only runs inside a migration. On a host that is already
encrypted, including one converted earlier with console unlock:

1. Deploy a generation that contains `luxnix-setup-remote-unlock` (every
   boot-LUKS generation built from this release) and run
   `sudo luxnix-setup-remote-unlock` on the host. It verifies the encrypted root,
   creates `/etc/luxnix/initrd-ssh/ssh_host_ed25519_key` once and prints the
   `known_hosts` line. Rerunning it keeps the identity and prints the line again.
2. Record the management inputs in the inventory. In shared variables give the
   host and every allowed client an `ip_local` and the same `network_cluster`
   under `generic_settings.network.hosts`; in the host YAML set
   `storage.operatorUnlocked.remoteUnlock` (`enable`, `interface`,
   `kernelModules`, `address`, optional `gateway`, `authorizedKeys`). Read the
   interface and driver on the host:
   `basename "$(readlink /sys/class/net/<interface>/device/driver)"`. Reserve the
   static address outside the DHCP pool, or reserve the lease for it.
3. Regenerate, build and install with `boot`. A missing identity stops the
   switch and names the command from step 1.
4. With someone at the console as fallback, reboot, pin the printed line and
   unlock once from each allowed client:
   `ssh -tt -p 2222 root@<address>`. Only then rely on it.

An operator outside the site reaches the endpoint through an allowed host on the
same LAN: `ssh -tt -J admin@<jump host> -p 2222 root@<address>`. The endpoint sees
the jump host's LAN address, so that address must be an allowed source, and the
jump host must itself be running. Hosts that share one power circuit and all
wait for a passphrase cannot unlock each other; keep one always-on entry point
per site, or accept a console visit after a site-wide outage.

A USB network adapter is a weak management interface: its name follows the port
it is plugged into and it needs the USB host-controller and adapter drivers in
the initrd. Prefer the built-in wired port.

The dedicated key sits in the **unencrypted initrd**, so it is used for unlock
only. The current controller-signed Secure Boot policy requires an empty
`boot.initrd.secrets`, which is incompatible with this host-local SSH host-key
method. Hosts using that policy need a compatible signing and initrd identity
provisioning design before enabling remote unlock; keep Secure Boot as configured.
Fresh installation uses console unlock by default.

### Readiness observations versus admission

`devenv shell storage-readiness --limit <host>` collects observations. Private
request YAML with `storage_readiness_mode: admit`, the expected host and layout and
the exact attached serials also checks probes, boot generations and swap, still
read-only. Full reports are sensitive, gitignored files under
`cmdb/storage-readiness/`. Admission is a readiness signal; restore proof and
erasure approval come from their own steps.

## Snapshot backups from the existing gc-09 and gc-10 installations

After connectivity checks, run `devenv shell storage-migration-snapshot` with the
host, a unique snapshot ID, the root become user and a private sudo password file.
It serializes operations, stops declared writers, freezes inner filesystems, keeps
read-only Btrfs snapshots and restarts only previously active services. Coverage
is defined in `lx_administration/storage/migration-policy.yml`; update it when
hosts, paths or writers change. Snapshots cover the listed subvolumes; whole-disk
images, GPT/EFI and controller vault custody need their own copies.

Retries verify the original identities; each capture window stays separate.
`migration_snapshot_action=status` reads the journal and
`migration_snapshot_action=recover` retries thaw and service recovery. Keep
journals, locks and snapshots until recovery succeeds.

`devenv shell storage-recovery-custody prepare` creates dedicated age identities on
encrypted controller storage and independent custodian media, testing each against
a challenge; `verify` repeats the checks. `devenv shell storage-migration-backup`
takes the backup mountpoint, host, snapshot ID and both identities (see the command
catalog), reads only recorded snapshots, encrypts to both recipients and
authenticates each copy before publishing. Backup media hold ciphertext only.

`.partial` and `.unverified` files are incomplete. Receipts bind source, producer,
snapshot identities and recipients. `--recover-existing` authenticates existing
archives against the current source before adopting them. Keep the identities that
existing archives need. Restore into an empty, isolated, encrypted Btrfs directory
with authenticated `age` decryption, decompression and `btrfs receive`, checking
every pipeline status, then validate the database and old media.

### Full-disk image of the original NVMe

Shut down and boot trusted media. Identify the source by serial, keep its
partitions unmounted, disable swap and automounting, and identify the destination
independently. Stream the whole device, GPT and EFI included, into a new encrypted
archive, check every pipeline status, and verify byte count and hash through a full
decrypt and decompress. Keep failed artifacts for review. Restoring the image
replaces newer writes and needs its own authorization.

## Acceptance, recovery and rollback limits

Acceptance is an offline cold boot with one root unlock, automatic secondary
unlock, local SOPS where used, administrator login, sudo and SSH, and database and
application startup. Query restored data, decrypt old media and test the
independent recovery credentials. On a disposable copy, confirm that missing data
disks or invalid secondary keys stop writes. Check that key identities hold across
activation, reboots and a normal signed update. Record physical evidence separately
from VM results.

A missing mapping or key calls for identity and custody investigation with the
original keys. Application backups need their own application keys. In-place
conversion has the tested backup as its rollback, which returns data to the backup
point. Keep backups and containers until signed-off acceptance.

## Temporary compatibility and removal

`legacy-containers` hosts, including the explicit gc-10 exception, keep their
container UUIDs, bind maps, original keys and recovery tools, and normal rebuilds
leave them as they are. gc-10's migration target encrypts both existing Btrfs
partitions independently, without introducing MD RAID or changing their partition
layout. The system partition uses `cryptroot`; the data partition uses
`luxnix-app-storage`. Existing containers remain readable on their original
filesystems until separate retirement after acceptance. Application and PostgreSQL
subvolumes live on the encrypted data partition, and secondary unlock keys live
only on encrypted root. The external Backup export disk is outside the target
selection and is not converted or formatted.

A recovery console, independent backups, matching disk identities and cold-boot
acceptance are still required. MD arrays and multi-member Btrfs conversions remain
unsupported; they require a separately reviewed workflow. See
[legacy recovery](legacy-storage-recovery.md) for guarded activation and backups.
Applications start only on encrypted storage, and disk swap stays off.

Select compatibility in the host inventory, validate with
`devenv tasks run autoconf:check`, compare, and regenerate with
`devenv tasks run autoconf:generate`. Container `migration.enable` controls copying
only. Remove exceptions and recovery material after supported conversion, physical
acceptance and the retention decision; each host's migration is proven on the host.

<a id="reprovision-and-restore-explicit-destructive-operator-action"></a>
## Retired destructive installation paths

Old erase and restore plans are kept unchanged as evidence. Fresh installation uses its own
reviewed bundle and operation-specific consent, separate from preservation
journals. Preservation supports the layouts above and keeps the data in place.

## Coordinated hub snapshots

The gs-02 coordinator stops declared application and database writers, creates a
fresh PostgreSQL dump in root-controlled `/run`, copies encrypted media, verifies
checksums and atomically publishes the restore point. Its journal restarts only
previously active units; after a failed recovery,
`/run/luxnix-hub-backup/recovery.json` stays for `luxnix-hub-backup recover`.
External or manual writers need their own quiescence. Destinations are separate
real paths on encrypted storage. Restore and cold-boot acceptance follow.

## Repository verification and physical evidence

Run the focused suites in [Testing](testing-nixtests.md), plus:

```sh
nix build .#checks.x86_64-linux.boot-storage-fresh --no-link -L
nix build .#checks.x86_64-linux.boot-storage-in-place --no-link -L
nix build .#checks.x86_64-linux.boot-default-hold --no-link -L
nix build .#checks.x86_64-linux.hub-backup --no-link -L
devenv tasks run nix-quality:check
devenv tasks run docs:check
python scripts/lint_structure.py
```

VMs use disposable media and synthetic credentials. Physical boot, production
Secure Boot custody and clinical restoration are confirmed on the hosts, and
readiness is tracked in the feature tracker.
