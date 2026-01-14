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
