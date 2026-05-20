This folder contains Jinja templates for auto-generating LuxNix configs.

Goal of this implementation is to minimize manual edits to generated NixOS and
Home Manager configs and to keep role selections centralized.

How generation works (high level):
- Inputs: Ansible inventory + group/host vars + role selections in
  `conf/_nix-configs/*.yml`.
- Templates: `conf/nix-templates/systems/...` and `conf/nix-templates/homes/...`.
- Outputs: `systems/x86_64-linux/<host>/default.nix` and
  `homes/x86_64-linux/<user>@<host>/default.nix`.

Regenerate configs:
- `python scripts/autoconf-pipeline.py`
- Or `devenv tasks run autoconf:finished` (if available in your environment)

Notes:
- Treat generated system/home configs as derived outputs; update inputs instead.
- Role files under `conf/_nix-configs/` are managed by the pipeline and may be
  overwritten on regeneration.

System config inputs:
- `group_roles`, `role_roles`, `host_roles` render under the generated `roles`
  attrset.
- `group_services`, `role_services`, `host_services` render under the generated
  `services` attrset.
- `group_luxnix`, `role_luxnix`, `host_luxnix` render under the generated
  `luxnix` attrset.
- `group_nixos`, `role_nixos`, `host_nixos` render as top-level NixOS module
  options. Use these for namespaces not covered above, such as `boot.*`,
  `networking.*`, `hardware.*`, `nix.*`, `programs.*`, `systemd.*`, or
  `users.*`.
- Keep `roles.*`, `services.*`, and `luxnix.*` settings in their dedicated
  sections above to avoid duplicate top-level attrset definitions in generated
  files.
- `group_imports`, `role_imports`, `host_imports` append raw Nix import
  expressions to the generated `imports` list.

Example:

```yaml
host_imports:
  - ./hardware-extra.nix
host_nixos:
  networking.firewall.allowedTCPPorts:
    - 22
    - 443
  boot.kernel.sysctl."net.core.rmem_max": "16777216"
```

Values may be native YAML booleans, numbers, lists, and attrsets. String values
that are already Nix expressions, for example `pkgs.linuxPackages_6_6` or
`lib.mkForce "/home/admin/luxnix"`, are preserved as raw Nix expressions.
