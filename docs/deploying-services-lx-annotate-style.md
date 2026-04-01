# Deploying A LuxNix Service `lx-annotate`-Style

This document explains how to build and deploy a LuxNix service using the same secure pattern now used by `lx-annotate`.

The important architectural point is:

- this is already a good reusable pattern
- but it is not yet a universal platform abstraction automatically applied to every service

Today, the pattern is integrated across:

- `luxnix.vault.client`
- `roles.managed-secrets`
- the `services.luxnix.lxAnnotateLocal` module

If you want another service to behave the same way, you should deliberately copy this structure rather than assuming Vault integration is automatic for all LuxNix services.

## What “`lx-annotate`-Style” Means

A service deployed `lx-annotate`-style follows this chain:

```text
vault-auth-setup.service
  -> managed-secrets-setup.service
    -> <service-specific secret or mount gate>
      -> <service runtime units>
```

In concrete terms:

1. LuxNix bootstraps Vault access for systemd services.
2. `managed-secrets` materializes local secret files.
3. A service-specific gate uses those files.
4. The application starts only after the gate succeeds.

For `lx-annotate`, the service-specific gate is:

- `lx-annotate-encrypted-data.service`

That gate unlocks and mounts the encrypted data directory before the app starts.

## What Is Already Reusable

The following parts are already generic LuxNix building blocks:

### 1. Vault bootstrap

Use:

- `luxnix.vault.client`

This gives you:

- explicit systemd-managed Vault auth
- runtime Vault environment at `/run/luxnix/vault/vault.env`
- support for:
  - `tokenFile`
  - `approle`
  - predeclared `environmentFile`

### 2. Secret materialization

Use:

- `roles.managed-secrets.customSecrets`

This gives you:

- create-if-missing behavior
- refresh-on-boot behavior
- atomic rewrites
- consistent permissions and ownership
- service integration with `managed-secrets-setup.service`

### 3. Safety testing

Use:

- the `nixtest` suite in [tests/nixtest](/home/admin/luxnix/tests/nixtest)

This already checks the common Vault and reachability contracts and should be extended whenever a new service adopts this pattern.

## What Is Still Service-Specific

The following part is not yet a generic LuxNix abstraction:

- the service-owned runtime gate

For `lx-annotate`, that gate is a LUKS mount unit. For another service, it might instead be:

- a decrypted data mount
- a generated TLS asset step
- a certificate fetch step
- a database credential rendering step
- a one-time bootstrap service

LuxNix does not yet provide a single generic option like:

```nix
services.<name>.vaultBackedRuntime.enable = true;
```

that would automatically create the whole chain for arbitrary services.

So the model today is:

- generic Vault bootstrap
- generic secret delivery
- service-specific runtime gate
- service-specific runtime wiring

That is good integration, but not yet full platform generalization.

## The Recommended Deployment Recipe

To deploy a new service `lx-annotate`-style, follow these steps.

### Step 1. Define a clear service boundary

Decide:

- which files or directories are sensitive
- which secrets must come from Vault
- whether the app needs a service-owned mount or unlock step
- which units must fail closed if those assets are missing

You should explicitly separate:

- code/runtime path
- data path
- secret material

`lx-annotate` does this by keeping:

- app code in the service-user-owned runtime path
- encrypted data outside the app path
- secret files in `/etc/secrets/vault`

### Step 2. Bootstrap Vault for systemd

Configure:

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

This ensures system services do not depend on an ambient shell environment.

### Step 3. Materialize node-scoped secrets through `managed-secrets`

Declare service-specific secrets as `customSecrets`.

Example:

```nix
roles.managed-secrets.customSecrets.my_service_secret = {
  path = "/etc/secrets/vault/my_service_secret";
  owner = "root";
  group = "root";
  permissions = "400";
  refreshOnBoot = true;
  description = "Vault-backed secret for my service";
  customScript = true;
  generator = ''
    VAULT_PATH="secret/data/nodes/${config.networking.hostName}/my-service"
    ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
      | ${pkgs.jq}/bin/jq -er '.data.data.secret_field' \
      > "$TARGET_FILE"
  '';
};
```

Rules to follow:

- use `refreshOnBoot = true` for externally sourced secrets
- keep root-only permissions unless the service genuinely requires otherwise
- prefer hostname-scoped Vault paths for node-local assets

### Step 4. Create a service-specific runtime gate

This is the part `lx-annotate` adds on top of the generic stack.

For a new service, create a dedicated systemd unit that:

- runs after `managed-secrets-setup.service`
- requires `managed-secrets-setup.service`
- consumes the delivered secret files
- produces the runtime state the application needs
- fails closed if prerequisites are missing

Examples:

- unlock a LUKS device
- mount a decrypted data volume
- write a rendered config file
- fetch a certificate bundle

For `lx-annotate`, that gate is:

- `lx-annotate-encrypted-data.service`

### Step 5. Gate the application service on the runtime unit

Your runtime services should:

- `after = [ "<runtime-gate>.service" ]`
- `requires = [ "<runtime-gate>.service" ]`
- use `RequiresMountsFor` where mounted data paths are involved

This is the key fail-closed behavior:

- Vault failure blocks secret delivery
- secret delivery failure blocks the runtime gate
- runtime gate failure blocks the app

### Step 6. Propagate only the runtime contract, not raw Vault state

The application should not talk to Vault directly unless that is a deliberate design choice.

Prefer to pass in:

- local file paths
- mounted directories
- runtime environment variables that point at those files

For example, `lx-annotate` consumes:

- `LX_ANNOTATE_ENCRYPTED_DATA_DIR`
- `LX_ANNOTATE_MASTER_KEY_FILE`

It does not fetch the LUKS key from Vault itself.

That separation keeps the application simpler and keeps Vault trust concentrated in the system layer.

## Minimal Template

This is the smallest useful mental template for a new service:

```nix
{
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

  roles.managed-secrets.customSecrets.my_service_secret = {
    path = "/etc/secrets/vault/my_service_secret";
    owner = "root";
    group = "root";
    permissions = "400";
    refreshOnBoot = true;
    description = "Vault-backed secret for my service";
    customScript = true;
    generator = ''
      ${pkgs.vault}/bin/vault kv get -field=secret_field \
        secret/data/nodes/${config.networking.hostName}/my-service \
        > "$TARGET_FILE"
    '';
  };

  systemd.services.my-service-runtime-gate = {
    after = [ "managed-secrets-setup.service" ];
    requires = [ "managed-secrets-setup.service" ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "/path/to/runtime-gate-script";
      RemainAfterExit = true;
    };
  };

  systemd.services.my-service = {
    after = [ "my-service-runtime-gate.service" ];
    requires = [ "my-service-runtime-gate.service" ];
    serviceConfig = {
      ExecStart = "/path/to/my-service";
    };
  };
}
```

## Safety Rules

If you want a new service to be truly `lx-annotate`-style, keep these rules:

### 1. Do not rely on ambient Vault access

Use `luxnix.vault.client` and systemd ordering.

### 2. Do not let the app start before secrets are materialized

Use `after` and `requires`.

### 3. Do not expose raw Vault secrets to the application unless necessary

Prefer local files or runtime gates.

### 4. Do not widen secret permissions casually

Start with:

- `root:root`
- `0400`

and only relax if a real runtime need exists.

### 5. Keep node-local assets hostname-scoped

Use a path template like:

```text
secret/data/nodes/{hostname}/my-service
```

### 6. Add `nixtest` coverage when you add a new service

At minimum, add:

- source-contract tests for secret delivery and service ordering
- reachability tests if boot failure could affect administrative access

## When To Generalize Further

If multiple LuxNix services start repeating the same structure, the next platform step would be to extract a reusable abstraction for:

- Vault-backed hostname-scoped custom secrets
- service-owned runtime gates
- standardized service dependency wiring
- standard `nixtest` fixture patterns

That would turn the current pattern from:

- “well integrated around `lx-annotate`”

into:

- “the standard LuxNix way to deploy secure Vault-backed services”

We are not fully there yet, but `lx-annotate` is now the reference implementation.

## Related Docs

- [lx-annotate Encrypted Data](/home/admin/luxnix/docs/lx-annotate-encrypted-data.md)
- [Nixtest Safety Suite](/home/admin/luxnix/docs/testing-nixtests.md)
- [Managed Secrets Role](/home/admin/luxnix/modules/nixos/roles/managed-secrets/README.md)
- [lx-annotate Service Module](/home/admin/luxnix/modules/nixos/services/lx-annotate-local/README.md)
