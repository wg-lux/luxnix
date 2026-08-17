# Autoconf pipeline

All pipeline options live in
[`autoconf/config.yml`](https://github.com/wg-lux/luxnix/blob/main/autoconf/config.yml).
Paths in that file are resolved relative to the configuration file, so the
pipeline behaves consistently even when invoked from another directory.

## Choose a task

| Need | Command | Effect |
| --- | --- | --- |
| Inspect and validate options | `devenv tasks run autoconf:check` | Reads configuration without generating files |
| Refresh reachable hosts | `devenv tasks run autoconf:refresh-facts` | Atomically updates successful local fact snapshots and retains failed hosts' last-known-good data |
| Require every host to refresh | `devenv tasks run autoconf:refresh-facts-strict` | Performs the same safe refresh but returns nonzero when any host is stale |
| Build a private local report | `devenv tasks run autoconf:generate-report` | Reads local snapshots and writes only the redacted HTML report |
| Regenerate configurations | `devenv tasks run autoconf:generate` | Updates derived Autoconf, NixOS, and Home Manager outputs |
| Inspect rendered Nix safely | `python scripts/autoconf-pipeline.py --nix-output /tmp/luxnix-render` | Renders existing merged data into a new external directory without modifying configured outputs |

Start with `autoconf:check`. Refresh facts only when current host information is
needed; report generation and configuration generation read the local snapshots
without contacting managed hosts.

## Options

The centralized options are:

- `paths.ansible_root`: source inventory, variables, roles, and CMDB facts
- `paths.output`: generated inventory and merged intermediate variables
- `paths.nix_output`: generated NixOS and Home Manager configuration root
- `paths.nix_templates`: Jinja template root
- `paths.report_output`: private, redacted inventory report destination
- `inventory.subnet`: managed IPv4 prefix, including the trailing dot
- `inventory.system_group`: Ansible group whose members receive generated
  NixOS system configurations
- `home.default_users`: Home Manager users used when merged host data does not
  declare `system_users`
- `home.state_version`: compatibility baseline written to generated Home
  Manager configurations

`paths.nix_output` is a generated destination and does not need to exist before
the first run; Autoconf creates the required system and Home Manager parent
directories when it publishes rendered files.

Automation can read one canonical, resolved value without parsing YAML itself:

```bash
python scripts/autoconf-pipeline.py --print-option paths.ansible_root
```

`--print-option` validates the configuration syntax and requested option, and
resolves relative paths, but does not require configured source paths to exist.
This makes it suitable for bootstrap scripts such as the fact refresh. Use
`--check` when the complete source and output layout must also be validated.

`paths.output` is the only configurable root for Autoconf intermediates. Its
fixed layout is represented by `AutoconfOutputLayout`: `inventory.yml`,
`merged_vars/`, `home_merged_vars/`, and `logs/`. Pipeline stages use this
shared layout instead of constructing child paths independently.

Likewise, `paths.ansible_root` is the only configurable Ansible source root.
`AutoconfSourceLayout` and its `AnsibleInventoryLayout` describe the fixed
`cmdb/`, `roles/`, `inventory/hosts.ini`, `inventory/home-hosts.yml`, and
inventory-variable paths used by every pipeline stage.

The fixed children of `paths.nix_templates` and `paths.nix_output` are
represented by `NixTemplateLayout` and `NixOutputLayout`. System and Home
Manager renderers therefore share one definition of their platform, host, and
`default.nix` paths. All five filesystem layouts live together in
`lx_administration.autoconf.layout`; `config.py` remains focused on loading and
validating user options. The public `nix.render_configurations` stage receives
the same `AutoconfConfig` object as the pipeline instead of duplicating its path
and Home Manager options across function arguments.

Within the import stage, `imports/main.py` loads and validates source data,
while `imports/artifacts.py` owns private staging and atomic publication of the
generated inventory and merged-variable files. Ansible YAML discovery lives in
`imports/sources.py`; the reusable recursive mapping operation is isolated in
`imports/merge.py`.

Autoconf keeps its two host concerns separate:

- `ansible/inventory/hosts.ini` contains remote Ansible targets and their
  connection addresses. Those addresses automatically become
  `generic-settings.network.hosts.<host>.ip-vpn`; do not repeat them in group
  or host variables.
- `ansible/inventory/home-hosts.yml` contains Home Manager hosts and their
  inherited `group_home_*` inputs. A Home-only host therefore needs no fake
  network address and is never selected by an Ansible `hosts: all` play.
- `ansible/inventory/host_vars/home/<host>.yml` contains the corresponding
  host-specific Home Manager values. The pipeline rejects missing or orphaned
  entries between this directory and `home-hosts.yml`. For a system-only setup,
  `home-hosts.yml` may contain `hosts: {}`; both `host_vars/home/` and the
  `conf/nix-templates/homes/` template subtree may be absent. When Home hosts
  are configured, Autoconf validates their host files and platform templates
  during generation.

Global group variables are split by responsibility under
`ansible/inventory/group_vars/all/`. Numbered filenames make their load order
explicit; see `ansible/inventory/group_vars/README.md` for the ownership map.

Validate the configuration and display every resolved option without writing
generated files:

```bash
devenv tasks run autoconf:check
# or
python scripts/autoconf-pipeline.py --check
```

Refresh local host facts when the inventory or managed hosts change:

```bash
devenv tasks run autoconf:refresh-facts
```

Each valid response atomically updates only its host's snapshot. Unreachable or
invalid hosts retain their last-known-good data and are named in the summary;
the default command succeeds when at least one host refreshed. CI and audits can
require a completely fresh inventory:

```bash
devenv tasks run autoconf:refresh-facts-strict
# or
./scripts/refresh-ansible-facts.sh --strict
```

Facts below `paths.ansible_root/cmdb` can contain sensitive hardware and
environment details. They are local, mode `0600`, and excluded from Git. The
generation pipeline reads these snapshots; it does not contact hosts. The
directory is optional for an initial run: when it is absent, Autoconf continues
without hardware facts. The fact-refresh command creates it when snapshots are
collected.

Generate an on-demand human-readable inventory report from the local facts:

```bash
devenv tasks run autoconf:generate-report
```

The report is written to `paths.report_output` with mode `0600`; the default
destination, `cmdb/index.html`, is gitignored.
By default it contains only host name, operating system, architecture,
virtualization, vCPU count, and RAM; addresses, serials, environment values,
inventory variables, and full host details are excluded. It may include
last-known-good snapshots named as stale by the most recent refresh summary.

Both standalone tools accept the same alternative configuration:

```bash
./scripts/refresh-ansible-facts.sh --config path/to/config.yml
python scripts/generate-cmdb-report.py --config path/to/config.yml
```

Generate NixOS and Home Manager configurations:

```bash
devenv tasks run autoconf:generate
# Short interactive alias:
devenv shell bnsc

# or
python scripts/autoconf-pipeline.py
```

For a reviewable render without replacing any repository output, use an
explicit, previously nonexistent directory outside the repository:

```bash
python scripts/autoconf-pipeline.py --nix-output /tmp/luxnix-render
```

This render-only mode reads the existing `paths.output/merged_vars/` and
`paths.output/home_merged_vars/` artifacts. It does not refresh facts, import
Ansible sources, modify `paths.output`, replace `paths.nix_output`, or evaluate
Nix. Every generated `.nix` file is normalized with the repository formatter
`nixfmt` before it is published, so templates do not need to reproduce its
whitespace or line-wrapping rules. A missing or failed formatter aborts the
render with an explicit error; an isolated target created for that failed run is
removed. The target must not already exist; this prevents accidental
overwrites. The command prints the resolved target after publishing the
complete rendered set. Regenerate normal outputs only with the regular
`autoconf:generate` task.

Use an alternative configuration when testing a new setup:

```bash
python scripts/autoconf-pipeline.py --config path/to/config.yml --check
```

Python callers use the same public configuration boundary:

```python
from lx_administration.autoconf import AutoconfConfig, run_from_config

config = AutoconfConfig.load("path/to/config.yml")
print(config.get_option("paths.ansible_root"))
run_from_config(config)
```

The pipeline runs these stages:

1. Load the Ansible inventory, CMDB facts, roles, and variables.
2. Write merged intermediate data below the configured Autoconf output path.
3. Render system and Home Manager configurations from the configured template
   directory into the configured Nix output path.

Run logs are written below `paths.output/logs`, independent of the invoking
working directory. The directory uses mode `0700` and log files use mode
`0600`. Logs contain stage, path, host, and validation-type metadata rather
than raw fact snapshots, merged host values, or rendered configuration values.

Merged host variables can contain detailed inventory data. Their
`merged_vars/` and `home_merged_vars/` directories therefore use mode `0700`,
and their YAML files plus the generated `inventory.yml` use mode `0600`.

Generated files are derived output. Change the Ansible inventory and variables,
templates, or `autoconf/config.yml` instead of editing generated system and home
files manually.

## Find the code and tests

The implementation lives in `lx_administration/autoconf/`. The machine-readable
[Autoconf test map](https://github.com/wg-lux/luxnix/blob/main/tests/autoconf.yml)
at `tests/autoconf.yml` assigns configuration, CLI, pipeline, source loading,
imports, rendering, operations, errors, layouts, and NixOS integration to their
focused test files. Use that map instead of adding new Autoconf coverage to an
unrelated catch-all module.

Run the focused suite from the repository root:

```bash
pytest -q tests/test_autoconf_*.py tests/test_ansible_autoconf_nixos_config.py
```
