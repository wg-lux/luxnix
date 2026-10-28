# Fleet Secure Boot with a controller-held key

`system.boot.secureBoot` is opt-in and currently disabled fleet-wide: hosts
use operator passphrase unlock, which does not depend on the boot chain.
Secure Boot only becomes meaningful together with TPM-bound unattended unlock,
and that path stays blocked on root integrity (ENC-09). When enabled, the NixOS module
`modules/nixos/system/boot` replaces systemd-boot with
[lanzaboote](https://github.com/nix-community/lanzaboote) `v1.2.0`.

One fleet PKI (PK, KEK, db) signs the boot chain. Its private keys never
reach a host. They exist only:

- age-encrypted in controller custody (default
  `~/.luxnix-secure-boot/fleet-pki.tar.age`, with its own passphrase); and
- decrypted in a private mode-0700 tmpfs while `secure-boot-keys` or
  `secure-boot-sign` runs, removed afterwards.

Hosts receive only public material from `conf/secure-boot/`: `db.pem` and
the signed firmware enrollment files `PK.auth`, `KEK.auth` and `db.auth`.
The module installs them under `/etc/luxnix/secure-boot/` once they exist in
the repository.

This key class is separate from volume unlock. A host or volume-release role
that is fully compromised cannot sign boot images.

## How a deployment is signed

lanzaboote's `lzbt` can only sign with a local key file. LuxNix therefore
splits installation:

1. **Host rebuild.** `nixos-rebuild boot` or `switch` (the `rebuild-host-boot` /
   `rebuild-host-switch` commands) sets the new system profile generation. The
   keyless install hook then runs lzbt with a private key path that never
   exists. Generations already signed on the ESP are registered; a new
   generation needs signing, so lzbt fails. The hook stops with
   `devenv shell secure-boot-sign <host>`. The previous boot entries stay
   unchanged and nothing is activated.
2. **Controller signing.** On the controller, `devenv shell secure-boot-sign <host>`:
   - builds the host toplevel from the reviewed checkout locally, so the signed
     content never comes from the host;
   - reads the host's current profile link over SSH with pinned host keys and
     refuses unless it points to exactly that build;
   - decrypts the PKI into private tmpfs, checks that its `db.pem` matches
     `conf/secure-boot/db.pem`, and runs the host's own lzbt install command
     for that one generation into a staging ESP;
   - copies the signed stub, systemd-boot, the fallback loader and the
     hash-pinned kernel and initrd to the host, and runs
     `sudo luxnix-boot-artifacts import` there.
3. **Host import.** `luxnix-boot-artifacts import` accepts only the expected
   ESP file names, verifies every stub and loader against the fleet `db.pem`
   with `sbverify`, never replaces a differing generation or content-addressed
   file, and publishes the files to the ESP.
4. **Finish.** On the host, run
   `sudo /nix/var/nix/profiles/system/bin/switch-to-configuration boot` (or
   `switch`). lzbt now finds the generation installed and signs nothing. The
   hook then re-verifies every stub and loader on the ESP, because lzbt does
   not re-check already installed stubs.

Kernel and initrd are not signed themselves; the signed stub pins their
hashes. `boot.initrd.secrets` is rejected at evaluation because the controller
cannot reproduce host-local initrd content.

## One-time key creation

On the deploy controller, from a private interactive terminal:

```bash
devenv shell secure-boot-keys
```

This refuses to run if custody or the public files already exist. It creates
the PKI in private tmpfs, exports the firmware enrollment files with
Microsoft's certificates (so GPU and storage option ROMs keep loading),
encrypts the PKI to custody (age prompts for the passphrase) and verifies the
readback. Then commit `conf/secure-boot/` and keep an independent encrypted
copy of the custody file under the recovery procedure. A lost custody file
means every host needs new keys enrolled in firmware.

## Per-host firmware enrollment

1. Confirm that the host uses UEFI and has a TPM 2.0 device (`bootctl status`).
2. Deploy and sign at least one generation (the steps above), then verify with
   `sudo sbctl verify`.
3. Put the firmware into Secure Boot setup mode (vendor-specific; needs
   physical or BMC access), then on the host:

   ```bash
   sudo luxnix-boot-artifacts enroll-firmware
   ```

   It refuses unless both loaders and an installed stub for the current profile
   generation verify against `db.pem` and the firmware is in setup mode. It writes db, KEK and then PK.
4. Reboot, enable Secure Boot if needed, and confirm
   `bootctl status` reports `Secure Boot: enabled (user)`.
5. Only after that, enroll TPM-bound unlock according to
   [Encrypted storage](operator-unlocked-storage.md).

A firmware reset to factory keys, a firmware update that changes the Secure
Boot databases, or a key replacement changes PCR 7. Any TPM binding to PCR 7
then needs recovery and re-enrollment.

## Fresh installation

`nixos-anywhere` and installer images cannot run controller signing during
installation. Install with `system.boot.secureBoot = false` for that host,
then enable it and follow the steps above.

## Current limits

- `secure-boot-sign` handles one host per run. A group-wide `--limit` run and
  a fleet status query are not implemented yet.
- No host has keys enrolled. Static tests and the controller signing test
  with the real lzbt/sbctl/sbverify are not boot evidence.
- PCR 7 and the signed stub cover the Secure Boot policy, kernel, initrd and
  command line, not the Nix store on an unencrypted root. Someone with
  offline write access to root can still change programs that run after
  unlock. Closing that gap needs an integrity-verified root (see the ENC-09
  work in `boot-encryption-acceptance.yml`).
