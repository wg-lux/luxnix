to do

customize facts gathering with custom, nix-provided scripts?

---

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
