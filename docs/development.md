# Development

Use this page for contributor-facing configuration changes. For initial host
installation, follow [Getting Started](./getting-started.md); for the complete
generation model, see [Autoconf and Local Inventory](./autoconf.md).

## Development environment commands

Enter the development shell with `devenv shell`. The `manage` wrapper provides
the supported local modes and points deployment requests to the host-specific
guide instead of guessing a target:

```bash
devenv shell manage help
devenv shell manage setup
devenv shell manage dev
devenv shell manage prod
```

The equivalent environment tasks are useful for automation. CUDA probing is
best-effort and does not block the general setup:

```bash
devenv tasks run env:setup
devenv tasks run env:setup-cuda
```

Local EndoReg database initialization is a composite task. Use its lower-level
tasks only when initialization and migration must be run separately:

```bash
devenv tasks run initialize-environment:endoreg-db
devenv tasks run initialize-environment:finished
devenv tasks run endoreg-db:init
devenv tasks run endoreg-db:migrate
```

These database commands change local state. Consult `devenv/commands.yml` for
the canonical invocation, effect summary, and risk label before automating
them.

## Know which file owns a change

- Edit reusable NixOS behavior below `modules/nixos/`.
- Edit reusable Home Manager behavior below `modules/home/`.
- Edit host inputs below `ansible/inventory/host_vars/` and shared defaults
  below `ansible/inventory/group_vars/`.
- Do not hand-edit generated files below `systems/x86_64-linux/` or
  `homes/x86_64-linux/`; regenerate them from their inputs.

The machine-readable ownership map is in `luxnix.yml` under
`artifact_ownership`.

## Reference central settings

NixOS modules can consume centralized host settings through `config`. For
example:

```nix
{
  config,
  ...
}:
let
  repositoryPath = config.luxnix.generic-settings.configurationPath;
in
{
  # Use repositoryPath when declaring the module's configuration.
}
```

The option is declared in
`modules/nixos/luxnix/generic-settings/default.nix`. Host-specific values
belong in the appropriate inventory variables and flow into generated Nix
through Autoconf.

## Install contributor packages

Use this workflow when adding command-line tools for EndoReg client machines:

1. Add tools required on all EndoReg clients to
   `modules/nixos/roles/custom-packages/default.nix`.
2. Prefer the `baseDevelopment` package list for general utilities.
3. Keep service modules limited to hard runtime dependencies.
4. Put host-only packages in the corresponding inventory variables or host
   configuration.
5. Rebuild and verify the target host:

   ```bash
   sudo nixos-rebuild switch --flake .#<host>
   command -v <package-command>
   ```

## Configure a Home Manager Git identity

Home profiles are generated. Set the Git identity in
`ansible/inventory/host_vars/home/<host>.yml`, not in the generated Home
Manager file:

```yaml
host_home_cli:
  cli.programs.git.userName: "Example User"
  cli.programs.git.email: "user@example.invalid"
  cli.programs.git.allowedSigners: "ssh-ed25519 <public-key> user@example.invalid"
```

`allowedSigners` is public verification material, not a private key or a
secret. Omit the host override to use the shared value from
`ansible/inventory/group_vars/group_home_cli.yml`.

Validate and regenerate after changing inventory inputs:

```bash
devenv tasks run autoconf:check
devenv tasks run autoconf:generate
```
