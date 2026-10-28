# Root integrity prototype

This is an isolated research spike, not a deployment profile or a readiness assessment. Its goal is to test whether a disposable NixOS image can boot a Nix closure from an ext4 store protected by dm-verity, with the expected root hash bound into its UKI. The fixture is implemented with an unsigned UKI and reconstructs `/etc` on a tmpfs root and excludes the host store and writable store overlays. A synthetic release sentinel stands in for secret release; it is not a credential or a real OpenBao unlock. The intended entry point is `devenv tasks run tests:root-integrity-vm`; consult the task and test implementation for what actually runs and its result. The matrix in [tests/root-integrity.yml](https://github.com/wg-lux/luxnix/blob/main/tests/root-integrity.yml) distinguishes passed VM checks from planned checks. The VM script passed in 50.00 seconds.

## Source trust boundary

These observations describe repository source, not an assessment of any particular deployed host. Actual enabled options, effective units, filesystem mounts, executable closures, credentials and access permissions must be inspected for each deployment. Read only metadata, not secret contents.

| Input or execution path | Source and consequence |
| --- | --- |
| Firmware, boot loader, kernel, initrd and command line | [boot module](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/system/boot/default.nix) selects the bootloader, including Lanzaboote when enabled, and installs public enrollment artifacts under `/etc/luxnix/secure-boot`. Secure Boot authentication of boot artifacts does not itself verify an independently writable root or Nix store. PCR 7 binding alone does not establish store integrity. |
| OpenBao process and config | [OpenBao module](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/luxnix/openbao/default.nix) generates store configuration and starts `${pkgs.openbao}` with it. The preflight executes store Python and `secret_storage.py` and `openbao_local.py`; activation checks TPM, enrollment state and credential acceptance; the Secure Boot check is conditional on its configuration. The program interpreter and dynamically linked libraries are also dependencies of each executed store binary. Their integrity requires coverage of the complete closure, not just a top-level executable. |
| Seal and volume credentials | The same module loads encrypted `seal.key` from the configured `/var/lib/openbao-bootstrap/` path using `LoadCredentialEncrypted`; [storage module](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/luxnix/operator-unlocked-storage/default.nix) loads `volume.unlock` from its configured path. [openbao_local.py](https://github.com/wg-lux/luxnix/blob/main/lx_administration/storage/openbao_local.py) explicitly describes header inspection as a policy filter; systemd must authenticate and unseal the credential. Mutable `/var/lib/openbao-local/raft/raft.db`, audit data and `/var/lib/openbao-bootstrap/pending-enrollment.cred` affect activation. Credential confidentiality or encrypted storage is not a proof of freshness or integrity of all surrounding execution paths. |
| Unlock and provisioning | The storage module packages [operator_migration.py](https://github.com/wg-lux/luxnix/blob/main/lx_administration/storage/operator_migration.py) and config into the store and runs it with store Python. It executes the configured store client via `runpy`, calls `cryptsetup`, and uses systemd TPM token or OpenBao release paths; recovery uses `systemd-ask-password`. Its service PATH and dynamically loaded libraries must be covered too. [openbao_enroll.py](https://github.com/wg-lux/luxnix/blob/main/lx_administration/storage/openbao_enroll.py) invokes `systemd-creds`, `cryptsetup` and systemd; enrollment and recovery are separate privileged workflows. `/etc/machine-id`, LUKS headers, container paths and mount/bind configuration influence decisions. |
| Post-unlock application | [runtime context](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/runtime-context.nix) defines `/var/lib/lx-annotate/.env.systemd` and `${service-user-home}/lx-annotate-wheel/.venv`. In wheel mode [composition](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/config.nix) installs packages into that mutable virtualenv and store wrappers execute its `bin` programs; application units run as the service user with the environment file. [migration service](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/subservices/lx-annotate-migrate.nix) invokes the effective application runtime. A verified store alone therefore does not authenticate wheel code, installed Python modules or environment-dependent behavior with access to unlocked data. The root-run [environment service](https://github.com/wg-lux/luxnix/blob/main/modules/nixos/services/lx-annotate-local/subservices/lx-annotate-runtime-env.nix) generates that file. |
| Runtime overrides and loaders | Writable `/etc/systemd/system` units and drop-ins, generators, environment files, `/etc/ld.so.preload`, module or configuration search paths, mutable executables or scripts, and bind mounts or overlays can redirect execution or alter the loader. `/var` and `/run` can supply such inputs if units, PATH, Python search paths or configuration reference them. These are threat surfaces to audit, not a claim that every one is currently enabled. `/etc` reconstructed from an authenticated closure must not accept persistent overrides before release. |

The trust chain must include firmware policy, authenticated UKI and embedded root hash, the selected verity data and hash devices, store closure (including interpreters and libraries), generated `/etc`, unit configuration, executable search paths and credentials. Availability of an encrypted persistent volume is separate from integrity of code that receives its plaintext. A privileged process or principal that can modify runtime code or systemd settings after verification remains within the trusted computing base. Root compromise after release is not prevented by dm-verity.

## Implemented fixture and planned evidence

The VM test constructs an ext4 verity store with a root hash embedded in an
**unsigned** UKI, a tmpfs root and reconstructed `/etc`. The image includes the
actual OpenBao binary and an individual helper source file, but the sentinel is
synthetic and no OpenBao release is exercised. The test checks read-only
mappings, policy rejection on restart and volatile state reconstruction.

The extended matrix exercises independent fresh qcow2 overlays of one immutable
base image: corruption of the required ext4 superblock, corruption of the first
verity hash-tree block while preserving its header, and replacement of the
entire store partition with an independently formatted ext4 filesystem while
retaining the original hash tree, UKI and GPT identities. Each negative boot
requires the corresponding kernel data/metadata corruption error and observes
absence of the release marker for 15 seconds. This is a bounded observation,
not proof of the full production tamper matrix. A final explicit switch to a
fresh overlay of the original verified image tests fixture recovery; no automatic
fallback is present.

Direct writes beneath `/etc/systemd/system` are rejected because that directory
is store-backed. The test then demonstrates the post-boot privileged threat:
root can replace the volatile symlink, install a real systemd drop-in and run an
executable from writable `/var`. The next boot must discard the executable,
drop-in and unit environment override before restoring the release sentinel.
This proves the tested tmpfs reconstruction boundary, not protection against
root compromise during an unlocked boot or arbitrary production persistent mounts.

The initial EROFS fixture stalled during filesystem discovery with the pinned
tools. The prototype uses ext4 with standard device probing instead of a custom
device-readiness override; the integrity mapping remains read-only dm-verity.
The fixed 4 GiB store partition is a disposable test size, not a production sizing policy.

Run `devenv tasks run tests:root-integrity-vm` from a normal Git-filtered flake checkout. The test imports its individual helper source file; do not pass an unfiltered repository root as a Nix path, which can copy unrelated local data into the store.

The corruption test targets a superblock needed to mount the filesystem. dm-verity checks blocks when read, not eagerly across the full image: corruption in an unread block need not be discovered before the sentinel. The root hash detects a mismatch with the selected store when affected blocks are read, but the unsigned fixture does not authenticate the UKI or its root hash. A forged UKI paired with a rehashed image is outside the current test.

Remaining checks include production persistent systemd, environment and loader injection paths, matching updates, mismatched image/UKI pairs, retired-generation rejection and independently authorized production rollback/recovery. Tests must establish that the relevant corrupted block or override path was exercised. A production release gate needs an explicit policy for validation before release; it cannot assume all blocks have been read. Verity alone does not prevent rollback to an older valid pair or root compromise after release. Recovery must not silently bypass the chosen gate.

This fixture does not prove firmware Secure Boot, hardware PCR policy, secret sealing, actual OpenBao, fleet behavior or post-unlock application integrity. Production decisions require signed UKIs and enrolled firmware keys, measured policy and credential lifecycle, exact mount and override audit, trusted immutable application runtime, authenticated persistent inputs, update/rollback policy, offline recovery, performance and hardware tests. Record real command output and assessor in the existing acceptance process; this specification is not a second readiness tracker.

## Recorded verification (2026-10-27)

- `devenv tasks run tests:root-integrity-vm` builds the same check as
  `nix build .#checks.x86_64-linux.root-integrity --no-link -L`; the VM script
  passed in 104.91 seconds, including clean boot, policy denial, actual unit and
  executable override reset, three independent rejected tamper boots and explicit
  recovery to the original verified image. Data corruption and store substitution
  reported corrupted data block 2; hash-tree corruption reported corrupted
  metadata block 1. Each negative boot observed no release marker for 15 seconds.
- `python -m pytest -q tests/test_root_integrity.py`: 1 passed, 0 failed,
  0 skipped in 11.12 seconds. An isolated fixture proves unrelated source files change neither
  the selected helper source nor the complete image derivation.
- `python -m pytest -q tests/test_encryption_primitives.py`: 5 passed, 0 failed,
  0 skipped. These existing component tests include hash-tree corruption and
  recomputed-root substitution; they do not extend the executed VM matrix.

Production inventory and unlock defaults were not changed. ENC-09 remains open.

## gc-09 deployment preparation

The user-selected candidate for controlled deployment is gc-09. Collect the
read-only baseline through the inventory-scoped wrapper:

```bash
devenv shell check-connectivity gc-09
devenv shell storage-readiness --limit gc-09
```

The readiness wrapper reports host identity, boot/current/profile generations,
firmware state, mounts and service state without reading credential values or
changing the host. A successful read-only baseline is not deployment approval.
Review the exact revision, locked inputs, built closure, recovery access and
maintenance scope before requesting approval for a specific deployment.

The shared EndoReg client role requires encrypted operator-controlled storage
and rejects unattended unlock while production root and runtime authentication
remain incomplete. This applies to the role across the fleet; gc-09 is a test
target, not a security exception. The disposable VM test does not install an
authenticated production root or authorize changing that gate.
