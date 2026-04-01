# lx-annotate Encrypted Data on LuxNix

This document describes how the LuxNix `lx-annotate` service handles encrypted local data, how Vault-based secret delivery is wired, and what host configuration is required to make the flow work safely on every node.

## Overview

The `lx-annotate` service module supports an encrypted local data directory through:

- a managed systemd unlock/mount unit:
  `lx-annotate-encrypted-data.service`
- a hostname-scoped Vault secret lookup
- the existing `roles.managed-secrets` service as the local secret materialization layer

The resulting runtime contract is:

- application code and wheel runtime live outside the data path
- the encrypted data volume is mounted at `services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir`
- the unlock key and LUKS UUID are delivered from Vault before the mount unit runs

## What Is Implemented

The current implementation does four concrete things:

1. It derives a hostname-scoped Vault path from `networking.hostName`.
2. It asks `roles.managed-secrets` to materialize a local LUKS key file and LUKS UUID file.
3. It orders `lx-annotate-encrypted-data.service` after that secret materialization step.
4. It orders the `lx-annotate` application services after the encrypted-data mount.

That means the LuxNix side already covers:

- hostname-based Vault lookup
- local secret file delivery
- LUKS unlock
- mount lifecycle
- app/service ordering

It now also covers:

- Vault client bootstrap for systemd services via `vault-auth-setup.service`
- refresh-on-boot for the Vault-backed lx-annotate files
- Vault-backed delivery of the application master key

## Secret Pathing

By default, Vault-backed lx-annotate encrypted-data secrets are read from:

```text
secret/data/nodes/{hostname}/lx-annotate
```

`{hostname}` is replaced with `networking.hostName`.

Example:

```text
secret/data/nodes/gc-06/lx-annotate
```

Expected Vault payload fields:

- `luks_key`
- `luks_uuid`
- `app_master_key`

These defaults can be changed through:

- `runtime.vaultManagedEncryptedData.vaultPathTemplate`
- `runtime.vaultManagedEncryptedData.vaultKeyField`
- `runtime.vaultManagedEncryptedData.vaultUuidField`
- `runtime.vaultManagedEncryptedData.vaultMasterKeyField`

## Local Secret Files

The module materializes three local files:

- `/etc/secrets/vault/lx_annotate_luks.key`
- `/etc/secrets/vault/lx_annotate_luks.uuid`
- `/etc/secrets/vault/lx_annotate_master_key`

Permissions:

- owner: `root`
- group: `root`
- mode: `0400`

This is intentional. Only the root-owned encrypted-data systemd unit should read these files.

## Service Ordering

The encrypted-data mount is guarded in two ways:

1. `runtime.managedEncryptedData.after`
2. `runtime.managedEncryptedData.requires`

When Vault-backed mode is enabled, both lists are automatically prefixed with:

- `managed-secrets-setup.service`

That means the unlock unit will not attempt to open the LUKS device before the secret provisioning step has run.

The application services also depend on the encrypted-data unit:

- `lx-annotate-boot`
- `lx-annotate-filewatcher`
- `lx-annotate-export-frames`
- data recovery / cleanup jobs

They also use `RequiresMountsFor = [ runtime.encryptedDataDir ]`.

When `luxnix.vault.client` auth bootstrap is enabled, the practical dependency chain becomes:

```text
vault-auth-setup.service
  -> managed-secrets-setup.service
    -> lx-annotate-encrypted-data.service
      -> lx-annotate-boot.service
      -> lx-annotate-filewatcher.service
      -> lx-annotate-export-frames.service
      -> lx-annotate-data-recovery.service
      -> lx-annotate-data-cleanup.service
```

## How the Mount Works

`lx-annotate-encrypted-data.service`:

1. reads the configured key file
2. reads `runtime.managedEncryptedData.luksUuid`, or falls back to `runtime.managedEncryptedData.luksUuidFile`
3. runs:
   `cryptsetup open UUID=<uuid> <mapperName> --key-file <keyFile>`
4. mounts `/dev/mapper/<mapperName>` at `runtime.encryptedDataDir`
5. applies the configured owner, group, and mode to the mount point

On stop, it:

1. unmounts the directory
2. closes the mapper with `cryptsetup close`

## Vault Review

The Vault integration is now structurally sound for multi-node rollout, with one deliberate remaining boundary: LuxNix can bootstrap Vault client usage, but the operator still needs to provide a trust root for Vault access.

### Strengths

- The secret lookup is node-specific by default.
- The LUKS material is not exposed to the application user.
- The unlock service runs as `root`, which matches the `0400 root:root` secret-file policy.
- The app itself only receives the mounted data path and, optionally, the application-layer master key file.

### Operational Properties

#### 1. Vault auth is now explicit, not ambient

LuxNix now supports a dedicated `vault-auth-setup.service` through `luxnix.vault.client`.

Supported modes:

- `tokenFile`
- `approle`
- or an explicitly provided `environmentFile`

The bootstrap writes a root-only runtime environment file at:

```text
/run/luxnix/vault/vault.env
```

and `managed-secrets-setup.service` consumes that file directly.

This removes the old dependency on root's interactive shell environment.

#### 2. Vault-backed lx-annotate files now refresh on boot

The lx-annotate Vault-backed files are now configured with `refreshOnBoot = true`, so each `managed-secrets-setup.service` run re-reads:

- `luks_key`
- `luks_uuid`
- `app_master_key`

from the hostname-scoped Vault path and rewrites the local files atomically.

This removes the old "delete the file first" rotation requirement for lx-annotate secrets.

#### 3. The LUKS UUID and key are split correctly, and failure handling is strict

If either file is missing or invalid:

- `managed-secrets-setup.service` fails
- or `lx-annotate-encrypted-data.service` fails
- and the app stack stays blocked behind the encrypted-data service

This is the correct fail-closed behavior, but it should be expected during bring-up.

## Recommended Configuration

```nix
services.luxnix.lxAnnotateLocal = {
  enable = true;

  runtime = {
    mode = "wheel";
    wheelPath = /path/to/dist/lx_annotate-0.0.2-py3-none-any.whl;
    wheelhousePath = /path/to/wheelhouse;
    encryptedDataDir = "/var/lib/lx-annotate/secure_data";

    managedEncryptedData = {
      enable = true;
      mapperName = "lx-annotate-data";
      fsType = "ext4";
      mountOptions = [ "defaults" ];
    };

    vaultManagedEncryptedData = {
      enable = true;
      vaultPathTemplate = "secret/data/nodes/{hostname}/lx-annotate";
      vaultKeyField = "luks_key";
      vaultUuidField = "luks_uuid";
      vaultMasterKeyField = "app_master_key";
      setupService = "managed-secrets-setup.service";
    };

    masterKeyFile = /etc/secrets/vault/lx_annotate_master_key;
  };
};
```

```nix
luxnix.vault = {
  enable = true;
  client = {
    enable = true;
    address = "https://vault.example.internal:8200";
    auth.method = "approle";
    auth.roleIdFile = /etc/secrets/vault/approle_role_id;
    auth.secretIdFile = /etc/secrets/vault/approle_secret_id;
  };
};
```

## How To Use This

The operational flow is now:

1. Configure `luxnix.vault.client` so systemd services can authenticate to Vault.
2. Configure `services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData.enable = true`.
3. Build or provide the `lx-annotate` wheel and set `runtime.wheelPath`.
   If you want fast and offline startup, also provide `runtime.wheelhousePath`.
4. Deploy with:

```bash
nh os switch . -- --accept-flake-config
```

On a healthy system this causes:

1. `vault-auth-setup.service` to prepare the Vault runtime environment
2. `managed-secrets-setup.service` to fetch and refresh the node-scoped Vault files
3. `lx-annotate-encrypted-data.service` to unlock and mount the LUKS-backed data directory
4. `lx-annotate-boot.service` and related services to start against that mounted path

The minimum host configuration is:

- `networking.hostName`
- `luxnix.vault.enable = true`
- `luxnix.vault.client.*`
- `services.luxnix.lxAnnotateLocal.enable = true`
- `services.luxnix.lxAnnotateLocal.runtime.mode = "wheel"`
- `services.luxnix.lxAnnotateLocal.runtime.wheelPath = ...`
- `services.luxnix.lxAnnotateLocal.runtime.wheelhousePath = ...` for offline wheel installs

## Expected Vault Payload

For a node with:

```text
networking.hostName = "gc-06"
```

the module expects Vault data at:

```text
secret/data/nodes/gc-06/lx-annotate
```

with a payload shaped like:

```json
{
  "data": {
    "luks_key": "<raw-key-material>",
    "luks_uuid": "01234567-89ab-cdef-0123-456789abcdef",
    "app_master_key": "<base64-or-raw-app-master-key>"
  }
}
```

The exact field names can be overridden, but those are the current defaults.

## Bring-Up Checklist

Before enabling the encrypted-data flow on a host, verify:

1. `networking.hostName` matches the intended Vault node path.
2. `luxnix.vault.client` is configured with either `tokenFile`, `approle`, or a declared `environmentFile`.
3. Vault contains `luks_key`, `luks_uuid`, and `app_master_key` for that hostname.
4. `/etc/secrets/vault/lx_annotate_luks.key`, `/etc/secrets/vault/lx_annotate_luks.uuid`, and `/etc/secrets/vault/lx_annotate_master_key` are created as `0400 root:root`.
5. `runtime.encryptedDataDir` is outside the repo and wheel paths.
6. `runtime.wheelPath` is set when `runtime.mode = "wheel"`.
7. If you want to avoid slow `pip` resolver/download work on the host, provide a populated `runtime.wheelhousePath`.

## Operator Verification

After deployment, the minimum verification sequence is:

```bash
sudo systemctl status vault-auth-setup.service
sudo systemctl status managed-secrets-setup.service
sudo systemctl status lx-annotate-encrypted-data.service
sudo ls -l /etc/secrets/vault/lx_annotate_luks.key /etc/secrets/vault/lx_annotate_luks.uuid /etc/secrets/vault/lx_annotate_master_key
sudo cryptsetup status lx-annotate-data
mount | grep lx-annotate
systemctl status lx-annotate-boot.service
```

If you want to inspect the exact node-scoped Vault lookup inputs:

```bash
hostname
systemctl cat vault-auth-setup.service
systemctl cat managed-secrets-setup.service
```

If the boot chain fails, debug in this order:

```bash
journalctl -u vault-auth-setup.service -b
journalctl -u managed-secrets-setup.service -b
journalctl -u lx-annotate-encrypted-data.service -b
journalctl -u lx-annotate-boot.service -b
```

## Safety Tests

LuxNix now ships a `technofab/nixtest` safety suite for this flow.

Run it from the repo root with:

```bash
nix run .#nixtests -- --workers 1
```

It currently verifies:

- Vault bootstrap is explicit
- lx-annotate Vault-backed secrets are root-only and refreshed
- `managed-secrets` handles custom secrets atomically
- lx-annotate Vault mode fails closed on missing prerequisites
- boot-time secret/bootstrap failure does not break SSH reachability
- failing application services do not make the node unreachable

## Remaining Boundary

The remaining requirement is intentional: the host still needs a real Vault trust root.

That means you must supply one of:

- a root-readable token file
- AppRole credentials
- or a prebuilt environment file

LuxNix now consumes those explicitly; it does not invent Vault credentials on its own.
