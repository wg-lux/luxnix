to do

customize facts gathering with custom, nix-provided scripts?


# Dynamic vars_file loading

**Will only load the first found file**

```yaml
pre_tasks:
  - debug: var=ansible_os_family
  - name: Load variable files
    include_vars: "{{ item }}"
    with_first_found:
      - "path/one"
      - "path/two"
```

## Connectivity check

The playbook `connectivity-check.yml` validates that Ansible can both reach a
target host and execute a simple command over SSH. Run it with the helper
script from the project root:

```bash
./scripts/check-connectivity.sh <inventory-host-or-group>
```

The script writes a timestamped log file to `./logs/`, defaulting to the `all`
inventory group when no target is provided. Pass `--` followed by any
additional Ansible arguments to forward them to `ansible-playbook`.
