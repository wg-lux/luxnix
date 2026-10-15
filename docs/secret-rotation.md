# Coordinated secret rotation

[secrets-management.yml](https://github.com/wg-lux/luxnix/blob/main/secrets-management.yml)
is the single coordination catalog for LuxNix, endoreg-db and LX-Annotate.
It contains public ownership, source references and ordered gates, never secrets
or host state. Production readiness remains exclusively in
[the lifecycle feature](https://github.com/wg-lux/luxnix/blob/main/feature-tracking/luxnix_secret_lifecycle_readiness.yml)
and the linked application feature trackers. A source check is not deployment acceptance.

From the LuxNix checkout, validate the three source trees and display one procedure:

```bash
devenv shell check-secret-rotation \
  --endoreg-db /home/admin/endoreg-db \
  --lx-annotate /home/admin/dev/lx-annotate \
  --family django_signing
```

Paths select source checkouts only. The checker validates the catalog schema,
gate order and referenced files, without reading credential files, invoking
remote commands or executing displayed steps. Application tests and installed
runtime checks establish behavior. Rotate one family and one reviewed scope at
a time: inventory, prepare, activate, verify, retire. There is no bulk apply or
automatic retirement. Missing evidence stops progression; repeat the owning
workflow's preview before resuming. Record versions, scope, operator, acceptance
results and recovery time in the appropriate feature tracker without secret values.

## Application keyrings

LuxNix owns private provisioning and atomic manifest publication. endoreg-db owns
the existing strict manifest parser and migration commands. LX-Annotate consumes
the handles and exports Django signing fallbacks. Keep all generations as private
immutable files; the manifest contains paths, not key values. Changing permissions
must never regenerate an established secret.

Use `services.luxnix.lxAnnotateLocal.django.identitySaltKeyringFile` for the identity
manifest. The existing `runtime.extraEnvironment` map carries
`DJANGO_SIGNING_KEYRING_FILE` and `LX_ANNOTATE_MASTER_KEYRING_FILE` into the common
systemd and maintenance environment. Values are absolute private manifest paths;
no key material may enter Nix evaluation or the store. For planned signing
rotation, first distribute the new key as a retiring reader while the old key
remains active; reload and verify all consumers before swapping active and
retiring generations. Reload again after the swap. Settings reload is required
for signing changes. Planned retiring signing keys permit session/token overlap;
compromised keys must be removed and affected sessions invalidated.

Identity salts and media master keys are durable data dependencies, not routine
passwords. Preserve all required old readers, backups and clinical relationships.
Follow [the backend procedure](https://github.com/wg-lux/endoreg-db/blob/main/docs/key_rotation.md)
for preview, apply, lease handling and retirement evidence. Do not use application
rotation to replace disk-encryption keys. Never transmit the media master key.

## Credentials and incidents

### Standard operator sequence

1. Select one family and one explicit host scope from the catalog. Hub AppRole
   credentials, certificates, node request secrets, media keys, identity salts
   and Django signing keys have different lifecycles. Payload rejection alone
   is not evidence that credentials need rotation.
2. Verify an encrypted backup and tested restore path, installed reader support
   and all consumers. Do not begin a data-key migration with a failed backup.
3. For planned application rotation, provision immutable private generations and
   an atomic keyring manifest. Distribute the new reader while retaining the old
   active generation, verify every reader, then switch the active generation.
   Validate file contents, ownership and permissions; a configured path is not
   proof that a usable key exists.
4. Preview `rotate_storage_secrets --include-hls` or `rotate_identity_salt`
   without `--apply`, using the installed production environment and service user.
   Missing identity evidence requires authenticated originals and the backend's
   private review procedure. Never guess identity values. Review application-level
   blocked counts: a successful process exit does not prove migration completion.
   Confirm the installed command's transaction semantics before applying.
5. Reload web and worker settings after signing-key activation and verify active
   and retiring readers. For hub credentials, follow the enrollment/rotation
   procedure and verify fresh authentication, certificates, both node records
   and a matching receiver receipt. Never distribute media master keys.
6. Retire only after previews, live readers, backups, replicas, offline workers
   and retained media generations are accounted for. Keep required retiring salts
   and media keys. Compromised signing keys must not remain as fallbacks.

For the distinctions between SSH keys, Linux sudo passwords, Vault unseal shares
and Vault enrollment tokens, use the [enrollment prerequisites](vault-hub-machine-enrollment.md#what-you-need-before-starting).
An unseal share unlocks the existing Vault; it is not a token. Never reinitialize
Vault to recover access. Record deployment evidence in the feature tracker,
not as dated incident narratives in this procedure.

Use the existing [admin password workflow](admin-passwords.md) and
[hub enrollment workflow](vault-hub-machine-enrollment.md) for their respective
families. Their terminal confirmation, pinned transport and recovery gates remain
mandatory. Re-enrollment preserves identity; it is not complete breach recovery.
Revoke Secret IDs, tokens, certificates and node request secrets at their owning
authorities as required by the incident procedure. Database, identity-provider,
recipient, local vault and disk credentials require their own reviewed procedure;
the catalog deliberately does not invent a generic replacement operation.
