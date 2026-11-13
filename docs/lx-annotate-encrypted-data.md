# LX-Annotate storage on LuxNix

LuxNix owns disk encryption. LX-Annotate consumes paths and its application key.
The [boot storage contract](boot-storage-migration.md#shared-encryption-contract)
is authoritative for disk layout, unlocking, mount checks and recovery.

## Rules

1. New installations use encrypted root. Existing legacy containers remain an
   OS compatibility layout, configured through `luxnix.storage.operatorUnlocked`.
2. LuxNix provides the mounted application path. The historical option
   `services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir` defaults to
   `/var/lib/lx-annotate/data`; it is a path, not a request to unlock a device.
3. LX-Annotate uses the same runtime paths in either layout. It has no disk UUID,
   passphrase, LUKS key or unlock-service setting.
4. LuxNix orders services after their required mounts and verifies protected
   storage. Missing or locked storage stops startup before writes reach an
   underlying unprotected directory. Configure the OS for the installed layout.
5. Application file encryption is separate from disk encryption. Preserve
   `runtime.masterKeyFile` and existing data during migration. A different disk
   layout never justifies generating a replacement application key.

## Retired configuration

The application options `runtime.managedEncryptedData`,
`runtime.vaultManagedEncryptedData`, and `runtime.encryptionService`, and the
`lx-annotate-encrypted-data.service` unlock unit have been removed. Configure
storage in the shared LuxNix module and pass the resulting paths to the service.
Existing shared legacy-container support remains available; no files are moved,
formatted or re-encrypted by this refactor.

## Check storage

```bash
findmnt -T /var/lib/lx-annotate/data
systemctl list-units 'luxnix-storage-*'
systemctl status lx-annotate-runtime-env.service lx-annotate.service
```

For service permissions and application key checks, follow
[machine secrets checklist](machine-secrets-checklist.md).
