LuxNix: explicit passphrase storage provisioning
Prepared 2026-10-29

Repository: https://github.com/wg-lux/luxnix
Base branch: lx-annotate_ollama
Base commit: 37036e5a557f7e75f6a8cad8aadce04a7dbca107

STATUS
The change is implemented and tested locally. It has not been deployed to gc-02.
GitHub publication was rejected with HTTP 403, Resource not accessible by
integration. No remote branch or pull request was created.

WHAT THE ERROR MEANS
The unlock service cannot find a file at the declared container path. That
can mean initial provisioning is missing, but it can also mean an existing
backing mount or container needs recovery. Establish which before creating
new storage. A service restart does not create the container.

The implementation gap is that the default passphrase boot policy had no
supported explicit provisioning backend. The controller selected passphrase,
but the host provisioner accepted only TPM or local OpenBao.

WHAT THIS PATCH CHANGES
- Adds passphrase to the existing storage-provision command.
- Requires the configured passphrase policy on both controller and host.
- Authenticates encrypted recovery records on the controller and the selected
  independent recovery host before invoking host provisioning.
- Creates a new private LUKS allocation with the escrowed random passphrase,
  publishes it safely, initializes ext4, and leaves its mapping open.
- Resumes interrupted provisioning with the same identity and credential.
- Refuses unreceipted existing containers, conflicting state and unexpected
  filesystems. The ordinary boot/unlock path still never creates storage.
- Documents deployment, migration and recovery-passphrase readback.

APPLY THE PATCH
Extract this archive. From your LuxNix checkout, inspect existing changes,
then substitute the extracted patch's actual path in these commands:

    git status --short
    git apply --check /path/to/luxnix-passphrase-storage.patch
    git apply /path/to/luxnix-passphrase-storage.patch
    git diff --stat

The patch was checked against the base commit above. Do not reset or discard
local changes if it conflicts with a newer checkout; reconcile the changes.
Use the same reviewed source revision on controller and target.

BUILD AND INSTALL THE UPDATED HOST HELPER
The existing-host workflow builds and then persistently switches the selected
host. On the controller, from the patched checkout:

    nix eval '.#nixosConfigurations.gc-02.config.system.build.toplevel.drvPath'
    nix build '.#nixosConfigurations.gc-02.config.system.build.toplevel' --no-link
    devenv shell check-connectivity gc-02

On gc-02, using its inventory-configured checkout (adjust only if your actual
reviewed checkout is elsewhere):

    sudo nixos-rebuild switch --flake /home/admin/dev/luxnix#gc-02 --accept-flake-config

The deployed luxnix-storage-provision helper must contain this patch before
applying provisioning. An initial switch may still report missing storage;
that is not a completed deployment. After preparing storage, repeat the switch
and require a successful exit and matching active/persistent system profiles.

PROVISION A CONFIRMED NEW VOLUME
On the controller, set RECOVERY_HOST to the actual selected independent
recovery custodian. The example name below must be replaced. It must differ
from both target and controller; the existing admin vault and its key must be
usable from the controller.

    RECOVERY_HOST=your-recovery-host
    devenv shell storage-provision provision --host gc-02 \
      --volume luxnix-app-storage --backend passphrase \
      --recovery-host "$RECOVERY_HOST"

Review the reported host, machine ID, container path, existence and backend.
Then apply the same operation:

    devenv shell storage-provision provision --host gc-02 \
      --volume luxnix-app-storage --backend passphrase \
      --recovery-host "$RECOVERY_HOST" --apply

If sudo needs authentication, use the existing --sudo-password-file option
with a protected private file, as documented in the updated runbook.

On gc-02, inspect all declared volumes:

    sudo luxnix-operator-storage status

If luxnix-secrets also needs initial provisioning, repeat the controller
preview/apply commands with --volume luxnix-secrets. If it already exists,
use its existing credential to unlock it; do not recreate it. Each new volume
requires at least its configured minimum capacity, 8 GiB by default, possibly
more based on source data. The existing free-space reserve remains enforced.

MIGRATE AND START
After both volumes are ready, use the existing cutover on gc-02:

    sudo systemctl start luxnix-storage-cutover.service
    sudo luxnix-operator-storage status

Cutover stops configured writers, verifies and publishes the final copy,
activates encrypted bind mounts, and restarts consumers. Source directories
are retained. If migration is already complete, use:

    sudo luxnix-operator-storage start

Repeat the normal system switch and require success. Check:

    readlink -e /run/current-system
    readlink -e /nix/var/nix/profiles/system
    systemctl --failed

The two system paths should agree. Inspect remaining failures individually.

BEFORE REBOOT
The new random 64-hex-character passphrase is the container's manual unlock
credential. It is separate from the Linux login password and the passphrases
of other volumes. Provisioning leaves the mapping open, but the next boot will
need the credential.

The controller returns primary_escrow, the path of its encrypted recovery
record. See the updated docs/operator-unlocked-storage.md section "Unlocking
a newly provisioned passphrase volume after reboot" for the readback recipe.
It uses the existing authenticated decrypt_secret API and displays the
credential directly in a private operator terminal. Verify recovery access
before rebooting. On the target, answer the systemd prompt locally or over
SSH with:

    sudo systemd-tty-ask-password-agent

VALIDATION COMPLETED
140 tests passed across:
- tests/test_operator_storage_migration.py
- tests/test_storage_provision.py
- tests/test_local_enrollment.py
- tests/test_documentation_contract.py
- tests/test_devenv_command_catalog.py

The focused tests exercise real Ansible Vault encryption with disposable
synthetic credentials and mocked host/block-device operations. Existing
OpenBao and TPM cases are retained. One existing Passlib/Python deprecation
warning was emitted.

Structure validation passed for 23 manifests. git diff --check passed.
Ruff passed with the existing long-line findings excluded (--ignore E501).
The updated OpenBao VM guest passed Python syntax compilation.

Nix and devenv are unavailable in this environment. The documentation task's
underlying pytest checks were executed directly; Nix evaluation, system
builds, full VM tests and a physical gc-02 boot have not been verified.
The patch was applied to a temporary Git index at the stated base commit and
produced the exact tested tree.

FILES CHANGED
- lx_administration/storage/operator_migration.py
- lx_administration/storage/provision.py
- lx_administration/storage/structure.yml
- devenv/commands.yml
- docs/operator-unlocked-storage.md
- tests/test_operator_storage_migration.py
- tests/test_storage_provision.py
- tests/nixtest/openbao_local_guest.py
