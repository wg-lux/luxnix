# gc-10 boot applicability review — 2026-11-05

> Historical evidence only; generation numbers and host state below are dated observations.
> For current installation steps use the [quickstart](https://github.com/wg-lux/luxnix/blob/main/docs/boot-storage-quickstart.md).

## Decision

**Do not stage a new boot generation or schedule a reboot from the controller's
current checkout.** The installed gc-10 generation 156 has booted successfully
and is selected in the system profile and bootloader. The clean checkout on
gc-10 evaluates to `legacy-containers`, which fits its existing plaintext root
and two encrypted containers. A `boot-luks` generation does not fit these disks:
the root is not LUKS, and a rebuild cannot migrate or encrypt it. The current
controller checkout is dirty and has no identified, built gc-10 candidate.
gc-02's successful encrypted-root evidence from this checkout strengthens the
shared implementation case, but gc-10 still needs its own disk migration and
boot acceptance before selecting that layout.

Here, “boot” means `nixos-rebuild boot`, which changes the persistent profile
and next boot entry without activating the running services. Its successful
return would not establish that a reboot can unlock storage, preserve login,
or start the clinical application. This review is read-only; no boot staging,
activation, key change, disk operation, or reboot was performed.

## Evidence and source identity

Read-only inspection used SSH with host-key checking to the inventory target
`gc-10` (`172.16.255.110`) on 2026-11-05, approximately 08:04 CET.

| Item | Observed result |
| --- | --- |
| Host checkout | `/home/admin/luxnix`, clean, revision `656694ff18fc5de17db282c4b9adbc04679a3c81` |
| Host lockfile | SHA-256 `65bd23da94a0e9cf17e09ac9c17e8e33e85d55b7fc429d4cca0446e29f62c2f7` |
| Controller checkout | `/home/admin/luxnix`, revision `6900db128352fb73c878a0cc85e3c4902a42bf89`, 29 staged entries before this report; same lockfile hash |
| Running, booted, profile | All resolve to `/nix/store/2cslcviw3z9p4sari2qvnw9lrvf1nr0p-nixos-system-gc-10-26.05.20261021.da6dc0e` |
| Generation provenance | Generation 156 records configuration revision `ebf77783731f35afe5d94bd294707a13d685ae5e`; it differs from the host's current checkout revision |
| Closure identity | NAR hash `sha256-gycdi88G6jHER5hpsz7x853jmfFkiWCYXkj0xzoP970=` |
| Bootloader | systemd-boot current and selected entry `nixos-generation-156.conf`; firmware Secure Boot disabled |
| Storage | `/` is Btrfs on `/dev/nvme1n1p3`; `luxnix-app-storage` and `luxnix-secrets` are open LUKS containers; physical swap partition is inactive, zram swap is active |
| Application | `lx-annotate.service` and PostgreSQL active; web ExecStart uses the immutable LX-Annotate 1.7.5 runtime |
| System health | `systemctl is-system-running` reports `degraded`; `lx-annotate-identity-salt-migration.service` is failed and continued to fail on 2026-11-05 |

The canonical inventory selects `storage.operatorUnlocked.layout =
"legacy-containers"` and `migration.enable = false` for gc-10. Read-only Nix
evaluation in its clean checkout returned `legacy-containers`. The retained
container UUIDs and paths are recorded in `ansible/inventory/host_vars/gc-10.yml`.
The repository's boot acceptance YAML expressly says this is a retained
compatibility layout, not boot-LUKS acceptance. The new boot-LUKS disk target
in `systems/x86_64-linux/gc-10/disks.nix` requires an independently reviewed
backup, reprovisioning and restore before it can apply to the host.
The LX-Annotate deployment-source readiness check reports 0/6 required
criteria accepted, so no production release approval follows from this review.

## gc-02 history considered

The operator reports that gc-02 successfully verified encrypted-root boot from
this checkout on 2026-11-04. The local gc-02 repair record independently
documents Btrfs root on the open `cryptroot` LUKS2 mapping and a successful
read-only storage verifier. The November 4 `boot-storage` VM log from this
checkout also records a completed fresh encrypted-root installation, a later
generation boot and successful final `luxnix-verify-boot-storage` check. These
results provide concrete evidence for the shared root-unlock, boot and verifier
path; the prior report underweighted them.

The gc-02 repair document and its `installed: false` build-identity snapshot
were written before the operator's reported success. They cannot establish the
later gc-02 state. An attempted fresh SSH read of inventory address
`172.16.255.102` on 2026-11-05 was rejected with `Permission denied
(publickey)`, so this review cannot independently confirm that later physical
boot, its exact installed closure, or application acceptance. The gc-02 result
does not change gc-10's observed plaintext root or convert its existing
container files. It removes uncertainty about whether the shared design can
boot an encrypted root, while leaving gc-10's host-specific migration and
activation gates open.

## Recent failure and its bearing on boot

The documented gc-10 failure is an application generation mismatch. An October
8 `test` activation installed LX-Annotate 1.4.9 while the persistent generation
still selected 1.3.12. The October 12 reboot selected the older package and the
downgrade guard stopped startup. Earlier, a stale generation also downgraded
LX-Annotate and endoreg-db against newer database migrations. Thus a successful
live activation, or a working application now, cannot prove that an older or
newly staged boot generation is safe for the shared runtime and database.

The latest local gc-02 boot repair includes a regression for activation preparation:
NixOS activation snippets can continue after a command fails unless the wrapper
exits explicitly. The initial regression failed; the subsequent focused run
passed 154 tests. This was a repository test, not evidence of a gc-10 production
activation failure or a gc-10 rollout. The repair candidate identity recorded
in `.boot-repair-audited-build-identity.json` targets **gc-02** and predates
the operator's later reported success. It cannot be treated as a gc-10 candidate.

On gc-10, generation 156 was placed in the profile on November 4 at 12:40 CET
and the host booted it at 13:13 CET. The active/profile/booted match and current
boot entry support that this specific generation booted. They do not establish
that every service passed acceptance: the identity-salt migration unit is
currently failed. The available systemd status shows exit code 1 but does not
establish its application-level cause. That failure must be investigated before
claiming a healthy reboot. It should not be attributed to the local activation
regression without matching production logs.

## Conditions for a later boot staging decision

1. Select a clean, durable gc-10 release source and record its revision,
   lockfile, selected LX-Annotate wheel and Nix closure identities. Review the
   controller's unrelated staged changes and build the exact gc-10 target from
   the source that would be deployed.
2. Confirm the evaluated target remains `legacy-containers`, retains both
   container UUIDs, keeps migration disabled, and passes the storage and
   account pre-switch checks. A `boot-luks` target requires the separate
   console-attended disk migration and restore acceptance first.
3. Resolve the failed identity-salt migration unit and verify the application,
   PostgreSQL, protected mounts, login access and generation/package/database
   compatibility. Preserve the previous known-compatible generation and logs.
4. If staging is then approved, use the reviewed `rebuild-host-boot` workflow;
   verify the new profile and boot entry. Arrange console recovery and a
   separately authorized reboot, then verify `/run/booted-system`, mounts,
   services and clinical application acceptance. Do not use `test` as a
   production wheel-mode rehearsal.

## Evidence limits

No gc-10 candidate was built or activated for this review. No gc-10 production
activation transcript for a newer failed candidate was found; the repository
regression and the currently failed service are distinct facts. gc-02's later
operator-reported result was not independently rechecked over SSH.
The report judges applicability to the observed installed layout and source
state, not readiness of a future release or the physical cold-boot procedure.
