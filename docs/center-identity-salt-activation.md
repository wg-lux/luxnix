# Center identity salt activation

This runbook activates a shared identity salt for every machine of one center.
It applies to any center key. Currently `university_hospital_wuerzburg` (gc-02,
gc-06, gc-09, gc-10) is the only opted-in center. All commands need an operator
who is authorized for the named host; remote or secret state changes are marked.

Never print salt values. The commands below show metadata, manifests (paths
only) and SHA-256 receipts, which are public admission pins.

## Variables

Set these in every shell used below. Replace the example values; never run a
literal placeholder.

```bash
CENTER=university_hospital_wuerzburg   # roles.endoreg-client.defaultCenterKey
SITE=gc-09                             # one host of that center
SITE_POLICY="lx-hub-site-$(printf '%s' "$SITE.intern" | tr '.-' '__')"
KV=lx-hub-secrets                      # luxnix.vault.*.hubPki.kvMountPath
```

The center key must match `[A-Za-z0-9][A-Za-z0-9_-]*` (at most 128 characters).
To list a center's hosts from the flake:

```bash
for h in $(nix eval --json '.#nixosConfigurations' --apply builtins.attrNames | jq -r '.[]'); do
  nix eval --raw ".#nixosConfigurations.$h.config.roles.endoreg-client.defaultCenterKey" 2>/dev/null \
    | grep -qx "$CENTER" && echo "$h"
done
```

## Opting a center in

Both sides are inventory changes, followed by `devenv tasks run autoconf:generate`:

1. `ansible/inventory/host_vars/gs-02.yml`: add the key to
   `vault.server.hubPki.sharedIdentityCenters`. Every site of the center must be in
   gs-02's `luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes` with
   `centerKey = "<center>"`, otherwise reconciliation grants nothing.
2. For each site of the center: set `endoreg_client.defaultCenterKey` to the key,
   `luxnix.lxAnnotateLocal.django.centerIdentitySalt: "true"` under
   `host_services`, and `vault.client.auth.deferUntilProvisioned: "false"` under
   `host_luxnix`. Evaluation fails if the host's Vault enrollment is deferred.

## What the configuration does

| Side | Behavior |
| --- | --- |
| gs-02 (Vault custodian) | Reconciling a site of a listed center creates `$KV/centers/$CENTER/identity` once with compare-and-set (`salt` field, 64 hex characters) and grants that site read access to this one path. |
| Center site | `managed-secrets-setup` waits for `vault-auth-setup`, fetches the salt into root-only `/etc/secrets/vault/lx_annotate_center_${CENTER}_identity`, then `lx-annotate-identity-salts.service` enrolls it. |

The provisioner (`scripts/provision-identity-salts.py`) never rewrites a salt file:

1. The established machine salt stays at `/etc/secrets/vault/lx_annotate_identity_active`
   with its recovery copies `active.salt` and receipts `enrolled` in
   `/var/lib/lx-annotate-identity-salts/` and `<data>/.identity-salt-recovery/`.
2. The center salt is written as a new generation,
   `/etc/secrets/vault/lx_annotate_identity_center_${CENTER}`, plus
   `center-${CENTER}.salt` and `center-${CENTER}.enrolled` in both recovery
   directories.
3. Only after all of these are durable is the keyring manifest
   `/etc/secrets/vault/lx_annotate_identity_keyring.yml` atomically switched. For
   `CENTER=university_hospital_wuerzburg` it reads:

   ```yaml
   active: /etc/secrets/vault/lx_annotate_identity_center_university_hospital_wuerzburg
   allow_legacy_default_salt: true
   center_id: university_hospital_wuerzburg
   generation: 1
   retiring:
   - /etc/secrets/vault/lx_annotate_identity_active          # previous machine salt
   - /etc/secrets/vault/lx_annotate_identity_legacy_default  # default_salt
   schema_version: 1
   ```

   A host without a previous machine salt has only the `default_salt` entry under
   `retiring`.

New identities and new hub pseudonyms use the center salt. The machine salt and
`default_salt` stay as read-only retiring readers for existing hashes.

The unit fails closed (no LX-Annotate start) when the Vault source is missing,
any center copy or receipt disagrees with Vault, the manifest names another
center, or an enrolled machine salt has disappeared. It never generates a local
replacement.

## 1. Before deployment

- Every site of the center must be Vault-enrolled.
- Back up `/etc/secrets/vault/` and `/var/lib/lx-annotate-identity-salts/` on each
  site to protected storage, following the host backup procedure. These hold the
  only copies of each machine salt. The center salt is the only one that Vault can
  resupply.
- Record the outbound transfer state of each site (see *Hub records* below)
  before activation.
- Run the local checks:

  ```bash
  python -m pytest -q tests/lx-annotate/test_identity_salt_provisioning.py \
    tests/lx-annotate/test_identity_salt_enrollment.py
  nix eval '.#nixosConfigurations.gs-02.config.system.build.toplevel.drvPath'
  nix eval ".#nixosConfigurations.$SITE.config.system.build.toplevel.drvPath"
  ```

## 2. gs-02 first

1. Deploy the reviewed revision on gs-02 with the documented
   `rebuild-host-switch` workflow ([Deployment](deployment-guide.md)). This
   installs the reconcile tool that knows the center list.
2. Create the center salt and grant the site policies. Run the documented
   enrollment wrapper from the controller. It prompts once for the Vault
   enrollment token and once for the shared sudo password, then reconciles every
   reachable configured site in one run. This changes Vault and site state:

   ```bash
   devenv shell enroll-reachable-hub-sites --ask-become-pass
   ```

   The first reconciled site of the center creates the salt. Later sites only
   reuse it and add the read grant to their own policy. Existing site tokens pick
   up the grant immediately, because Vault resolves policies by name. The wrapper
   reports unreachable sites; rerun it once they are online. If the sites use
   different sudo passwords, use `--ask-sudo-password` instead. To limit the run
   to one site, add `--site "$SITE"`.
3. Verify on gs-02, without reading the value. Use a short-lived administrative
   token, as in [Machine Enrollment](vault-hub-machine-enrollment.md):

   ```bash
   vault kv metadata get "$KV/centers/$CENTER/identity"
   # Expect: current_version 1, no deletion time.
   vault policy read "$SITE_POLICY" | grep -A2 'centers/'
   # Expect: only data/centers/$CENTER/identity with ["read"].
   ```

   A site of another center, or of a center that has not opted in, must show no
   `centers/` path, or only its own center. `current_version` must stay `1`. A
   higher version means the salt was replaced outside this workflow. Stop:
   enrolled sites will refuse it.

## 3. Center sites, one at a time

1. `devenv shell check-connectivity "$SITE"`, then deploy with `rebuild-host-switch`
   (remote state).
2. On the site, check the startup chain:

   ```bash
   sudo systemctl status vault-auth-setup.service managed-secrets-setup.service \
     lx-annotate-identity-salts.service lx-annotate-runtime-env.service lx-annotate.service
   sudo journalctl -u managed-secrets-setup.service -u lx-annotate-identity-salts.service -b --no-pager
   ```

3. Check the switch, which displays only paths and fingerprints:

   ```bash
   sudo cat /etc/secrets/vault/lx_annotate_identity_keyring.yml
   sudo sh -c "stat -c '%a %U:%G %n' /etc/secrets/vault/lx_annotate_identity_*"
   sudo cat "/var/lib/lx-annotate-identity-salts/center-$CENTER.enrolled"
   ```

   The center receipt must be identical on every site of the center; that proves
   they share one salt. The machine receipt (`enrolled`) must be unchanged and
   differ per site.
4. Then move to the next site.

## 4. Identity migration of existing records

`lx-annotate-identity-salt-migration.timer` runs
`rotate_identity_salt --apply --allow-partial` ten minutes after boot and hourly
after that. It matches each existing patient group against all readers (center,
machine, `default_salt`), then re-hashes verified groups to the center salt in
one transaction per group. Patient, examination and video IDs do not change.

```bash
sudo systemctl list-timers lx-annotate-identity-salt-migration.timer
sudo journalctl -u lx-annotate-identity-salt-migration.service --since today --no-pager
```

A failed migration unit means some groups are blocked (erased source identities,
collisions or pending examiner mappings). These groups stay unchanged and stay
readable through the retiring salts. Supply real reviewed evidence through
`django.identitySaltMigrationReviewFile`, as described in
[Database Ownership](database-ownership.md#reviewed-salt-migration-on-gc-02).
Never invent identities. Same-center matching also requires identical center
names and demographic inputs on every site.

## Recovering old videos and records

**On the site.** Old videos need no recovery step. The center salt does not
touch:

- Media encryption: the media master key is unchanged.
- Video content hashes: `raw_video_hash` is unsalted.
- Database foreign keys from videos to patients and examinations.

Historical patient hashes resolve through the retiring machine salt and
`default_salt`. The migration then moves verified groups to the center salt.

If salt files are damaged or lost:

| Situation | Recovery |
| --- | --- |
| One of the three copies of a generation is missing | `sudo systemctl start lx-annotate-identity-salts.service` restores it from the others. |
| Deployed center salt and both recovery copies lost | Restore from backup. The receipts guarantee that only the identical Vault value is accepted. |
| Machine salt lost in all three places | The unit fails with "Previously enrolled salt is missing". Restore `lx_annotate_identity_active` (or `active.salt`) from backup. Vault cannot supply it and no replacement is generated. |
| Copies disagree | The unit fails and keeps every copy. Compare the receipts and restore the copy whose SHA-256 matches its receipt. |

Do not delete `lx_annotate_identity_active` or any `*.salt` recovery copy after
activation. They are required to read hashes created before activation.

**On gs-02 (hub records).** gs-02 never receives salts or identity hashes. Hub
records use a pseudonym `HMAC(active salt, local UUID, "gs-02")`
(`endoreg_db/services/hub/hub_pseudonyms.py`):

- Videos already on gs-02 stay intact under their old pseudonyms. Re-sent media
  is deduplicated by the unsalted `raw_video_hash`.
- After activation, a patient or examination that was transferred **before**
  activation gets a **new** pseudonym on its next transfer, for example a
  follow-up examination. gs-02 then shows it as a separate pseudonymous patient.
  gs-02 cannot relink this by itself.
- The site can still compute the old pseudonym, because endoreg-db accepts an
  enrolled retiring salt in `get_hub_record_pseudonym(..., salt=<retiring>)`. A
  reviewed old-to-new pseudonym alias migration has to be built in endoreg-db
  and applied on gs-02. It is **not implemented** in endoreg-db 1.6.1.

Until that alias migration exists, choose one per site:

1. Activate and accept that follow-ups of previously transferred patients are not
   linked on gs-02. Nothing is lost; old records remain recoverable.
2. Stop `lx-annotate-celery-hub-transfer-worker.service` on the activated site
   until the alias migration is available.

## Do not

- Disable `centerIdentitySalt` after activation. Machine mode refuses the center
  manifest ("Established manifest differs") and LX-Annotate stays stopped. There
  is no supported switch back; fix forward.
- Change `defaultCenterKey` on an activated host. A manifest for another center
  fails closed.
- Remove the center from `sharedIdentityCenters` while sites depend on it:
  reconciliation would drop their read grant, and the next boot's
  managed-secrets refresh would fail.
- Write, delete or re-create the Vault center secret. Sites refuse any value
  that differs from their receipts.
