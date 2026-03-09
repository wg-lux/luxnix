# AGENTS.md

## Installing Packages (Contributor Policy)

Use this as the default rule when adding tools like `rg`, `fd`, `duf`, `dust`, or `dysk`.

1. Add Endoreg client tooling in:
   - `modules/nixos/roles/custom-packages/default.nix`
2. For common CLI tools, prefer the `baseDevelopment` list in that file.
3. Only add packages to service modules when they are hard runtime dependencies of that service.
4. For host-only needs, put packages in the host config under:
   - `systems/x86_64-linux/<host>/default.nix`
5. Validate by rebuilding a target host:
   - `sudo nixos-rebuild switch --flake .#<host>`
6. Verify on the host:
   - `which rg`
   - `which duf`
   - `which dysk`

This keeps package ownership predictable and avoids duplicate definitions across roles.
