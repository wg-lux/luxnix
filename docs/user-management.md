
# LuxNix Ansible User Management

This document provides an overview of how **LuxNix** uses Ansible to manage hosts, roles, configurations, and services. It is based on these file snippets:

1. **`luxnix/autoconf/group_vars.yml`**  
2. **`roles.yaml`**  
3. **`inventory/hosts.ini`**  
4. **`inventory/group_vars/gpu_client.yaml`**  
5. **`inventory/host_vars/gc-02.yml`**  

### Example Deployment Flow

1. **Add a host to `hosts.ini`** under the correct group (e.g., `[gpu_client]`).
2. **Create or update `host_vars/<hostname>.yml`** if the host requires special kernel settings, disk encryption settings, or GPU bus IDs.
3. **Adjust group-level variables** in `group_vars/<group>.yaml` if you need to enable or disable roles or services for the entire group.
4. **Run**:
    
    ```bash
	devenv tasks run autoconf:finished
    ```
    

## 1. Overview

LuxNix leverages **Ansible** to:

- Organize hosts into groups and apply group-level configurations.
- Manage host-specific settings using `host_vars/`.
- Enable and configure roles and services through variables (e.g., `group_roles`, `group_services`, `host_roles`, `host_services`).
- Automate generating NixOS configurations (or Linux configurations in general) via templates and variables.

### Key Concepts

- **Groups**: Defined in the Ansible inventory file (`hosts.ini`) and optionally in group-specific YAML files in `inventory/group_vars/`.
- **Hosts**: Listed in `hosts.ini`. Some have additional host-specific settings in `inventory/host_vars/<hostname>.yml`.
- **Roles**: Provide tasks, files, templates, and variables that can be enabled per group or host. For instance, `aglnet.client.enable: "true"` toggles the aglnet client role for that host or group.
- **Services**: Similar to roles but focus on specific services or configurations (e.g., `gpu-client-dev.enable`).

## 2. `luxnix/autoconf/group_vars.yml`

This file (`group_vars.yml`) provides default variables that apply (by default) to **all** hosts in the inventory, plus overrides for specific group categories (`base_server`, `gpu_client`, `gpu_server`, etc.). Below is an excerpt with some commentary:

```yaml
all:
  admin_password_file: '{{ local_users_passwords_dir }}/admin_raw'
  admin_password_file_source: '{{ luxnix_dev_repo }}/secrets/user-passwords/{{ inventory_hostname }}/admin_raw'

  aglnet_conf:
    backupNameservers:
      - 8.8.8.8
      - 1.1.1.1
    caPath: /etc/openvpn/ca.pem
    clientConfigDir: /etc/openvpn/ccd
    dhPath: /etc/openvpn/dh.pem
    domain: '{{ network_conf.domain }}'
    serverCertPath: /etc/openvpn/crt.crt
    serverKeyPath: /etc/openvpn/key.key
    subnet: 172.16.255.0
    subnetIntern: 255.255.255.0
    subnetSuffix: '32'
    tlsAuthPath: /etc/openvpn/tls.pem

  ansible_become_user: admin
  ansible_key_dir: '{{ luxnix_dest }}/secrets/ansible-vault-keys'
  ansible_key_source_dir: '{{ luxnix_dev_repo }}/secrets/ansible-vault-keys-source'
  ansible_python_interpreter: '{{ luxnix_dest }}/.devenv/state/venv/bin/python'
  ansible_ssh_private_key_file: ~/.ssh/id_ed25519
  ansible_user: admin

  authentication:
    agl_admin:
      id_ed25519_pub: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M
    dev_01:
      id_ed25519_pub: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK
    dev_02: {}

  group_luxnix: {}
  group_roles: {}
  group_services: {}

  local_users_passwords_dir: '{{ luxnix_dest }}/secrets/user-passwords/{{ inventory_hostname }}'
  luxnix_branch: main
  luxnix_dest: /home/admin/luxnix-production
  luxnix_dev_repo: /home/admin/dev/luxnix
  luxnix_repo: https://github.com/wg-lux/luxnix.git
  luxnix_secrets: null

  network_conf:
    domain: endo-reg.net
```

### Explanation

- **`all:`**: Defines variables that apply to all hosts globally.
- **`aglnet_conf`:** Configuration for an OpenVPN-based “agl network.”
- **`ansible_*`:** Standard Ansible variables (user, become_user, SSH private key, Python interpreter path, etc.).
- **`authentication`:** Here you can list public SSH keys for different roles or users (e.g., `dev_01`, `dev_02`).
- **`group_luxnix`, `group_roles`, `group_services`:** Empty dictionaries at this level, which you can override in specific groups or hosts.
- **`luxnix_dest` and `luxnix_dev_repo`:** Paths for the production environment and development repository.
- **`network_conf`:** Domain name `endo-reg.net` used for other references in your Nix/Ansible configuration.

Below `all:`, you have sections for **`base_server`**, **`gpu_client`**, **`gpu_server`**, **`hetzner_server`**, **`managed`**, **`openvpn_host`**, etc. For example, under `gpu_client`, you set:

```yaml
gpu_client:
  group_luxnix:
    nvidia_prime.enable: 'true'
    nvidia_prime.nvidiaDriver: '"beta"'
  group_roles:
    aglnet.client.enable: 'true'
    gpu-client-dev.enable: 'true'
    lx-anonymizer.enable: 'true'
    lx-anonymizer.user: '"PeterPan"'
  group_services: {}
```

**Interpretation**:

- `nvidia_prime.enable: 'true'` toggles NVIDIA-specific configuration in Nix.
- `lx-anonymizer.enable: 'true'` indicates that the `lx-anonymizer` role or module should be enabled, potentially using the user “PeterPan.”

## 3. `roles.yaml`

```yaml
ansible_main:
  files: []
  vars: null

common:
  files: []
  vars: null

dev-01-access:
  files: []
  vars: null

keycloak_host:
  files: []
  vars: null

managed:
  files: []
  vars: null

openvpn_client:
  files: []
  vars: null

openvpn_host:
  files: []
  vars:
    openvpn_host_vars:
      role_roles:
        aglnet.host.autoStart: 'true'
        aglnet.host.backupNameservers: '{{ aglnet_conf.backupNameservers }}'
        aglnet.host.cipher: AES-256-GCM
        aglnet.host.clientToClient: 'true'
        aglnet.host.dev: tun
        aglnet.host.enable: 'true'
        aglnet.host.keepalive: 10 1200
        aglnet.host.mainDomain: vpn{{  aglnet_conf.domain }}
        aglnet.host.networkName: aglnet
        aglnet.host.persistKey: 'true'
        aglnet.host.persistTun: 'true'
        aglnet.host.port: 1194
        aglnet.host.protocol: TCP
        aglnet.host.protocolLc: tcp
        aglnet.host.resolvRetry: infinite
        aglnet.host.restartAfterSleep: 'true'
        aglnet.host.subnet: '{{ aglnet_conf.subnet }}'
        aglnet.host.subnetIntern: '{{ aglnet_conf.subnetIntern }}'
        aglnet.host.subnetSuffix: '{{ aglnet_conf.subnetSuffix }}'
        aglnet.host.topology: subnet
        aglnet.host.updateResolvConf: 'false'
        aglnet.host.verbosity: '3'

postgres_host_backup:
  files: []
  vars: null

postgres_host_main:
  files: []
  vars: null

postgres_host_test:
  files: []
  vars: null

traefik_host_main:
  files: []
  vars: null
```

This file likely **maps roles to additional variables** or files that must be deployed. For instance, `openvpn_host` references `openvpn_host_vars.role_roles`, which sets a large set of OpenVPN parameters. These parameters can be consumed by your Nix or Ansible tasks to configure the OpenVPN server.

**Note**: This file does not appear to be the standard Ansible `roles/` structure. Instead, it seems to be a custom definition used to keep track of role-specific variables or to further define how roles are consumed in your environment.

## 4. `inventory/hosts.ini`

```ini
[main]
# Base Servers
s-01 ansible_host=172.16.255.1
s-02 ansible_host=172.16.255.12
s-03 ansible_host=172.16.255.13
; s-04 ansible_host=172.16.255.14

# GPU Servers
gs-01 ansible_host=172.16.255.21
gs-02 ansible_host=172.16.255.22

# GPU Clients
; gc-01 ansible_host=172.16.255.101
gc-02 ansible_host=172.16.255.102
; gc-03 ansible_host=172.16.255.103
gc-06 ansible_host=172.16.255.106
gc-07 ansible_host=172.16.255.107
gc-08 ansible_host=172.16.255.108
gc-09 ansible_host=172.16.255.109

[under_development]
s-02

[openvpn_host]
s-01

[base_server]
s-01
s-02
s-03
; s-04

[gpu_server]
gs-01
gs-02

[gpu_client]
gc-02
gc-06
gc-07
gc-08
gc-09

[managed]
s-01
s-02
s-03
gs-01
gs-02
gc-02
gc-07
gc-08
gc-09

[test_group]
s-03
gs-02
gc-09
```

### Explanation

1. **Groups** such as `[base_server]`, `[gpu_server]`, `[gpu_client]`, etc. are created to **categorize hosts**.
2. You can see which hosts belong to each group—for example, `[gpu_client]` includes `gc-02, gc-06, gc-07, gc-08, gc-09`.
3. Each group name corresponds to a section in `group_vars.yml` or a file like `inventory/group_vars/gpu_client.yaml` that can override default variables or define new ones (e.g., enabling roles).

**Notable**:

- You have a `[main]` group that lists all servers under the same heading.
- `under_development` is a subset for development or staging.
- `openvpn_host` group specifically has `s-01`, presumably for an OpenVPN server.

## 5. `inventory/group_vars/gpu_client.yaml` (Example Group File)

```yaml
group_roles:
  aglnet.client.enable: "true"
  gpu-client-dev.enable: "true"
  lx-anonymizer.enable: "true"
  lx-anonymizer.user: '"PeterPan"'

group_services: {}

group_luxnix:
  nvidia_prime.enable: "true"
  nvidia_prime.nvidiaDriver: '"beta"'
```

### Explanation

- This is a straightforward override file for the **`gpu_client`** group.
- By default, all GPU client hosts (`gc-02`, `gc-06`, etc.) will:
    - Enable the `aglnet.client` role (`"true"`).
    - Enable the `gpu-client-dev` role.
    - Enable and configure the `lx-anonymizer` role with `user: "PeterPan"`.
    - Configure `nvidia_prime` with `"true"` (to enable) and use the `"beta"` NVIDIA driver.

**Quoting rules**: Notice that for Nix, strings often need double quotes, so you see:

```yaml
lx-anonymizer.user: '"PeterPan"'
nvidia_prime.nvidiaDriver: '"beta"'
```

(Double quotes inside single quotes) to ensure Nix interprets these as literal string values.

## 6. `inventory/host_vars/gc-02.yml`

```yaml
---
template_name: "main"

host_roles:
  aglnet.client.enable: "true"

host_services: {}

host_luxnix:
  generic_settings.hostPlatform: '"x86_64-linux"'
  generic_settings.systemStateVersion: '"23.11"'

  generic_settings.linux.cpuMicrocode: '"intel"'
  generic_settings.linux.kernelPackages: '"pkgs.linuxPackages_latest"'
  generic_settings.linux.kernelModules:
    - "kvm-intel"
  generic_settings.linux.initrd.supportedFilesystems:
    - "nfs"
  generic_settings.linux.initrd.kernelModules:
    - "nfs"
  generic_settings.linux.initrd.availableKernelModules:
    - "xhci_pci"
    - "ahci"
    - "nvme"
    - "usb_storage"
    - "sd_mod"
  generic_settings.linux.supportedFilesystems:
    - "btrfs"
  generic_settings.linux.resumeDevice: '"/dev/disk/by-label/nixos"'
  generic_settings.linux.kernelParams: []
  generic_settings.linux.kernelModulesBlacklist: []

  nvidia_prime.nvidiaBusId: '"PCI:1:0:0"'
  nvidia_prime.onboardBusId: '"PCI:0:2:0"'
  nvidia_prime.onboardGpuType: '"intel"'
```

### Explanation

- **`template_name: "main"`**: Possibly used for Jinja or Nix templates to decide which template to render for this host.
- **`host_roles`, `host_services`**: Additional roles and services can be enabled/disabled specifically for `gc-02`.
- **`host_luxnix`**: Detailed hardware and kernel settings, which appear to feed into a Nix-based system configuration (e.g., kernel modules, microcode, file systems, etc.).
- The double quoting pattern (`'"x86_64-linux"'`) ensures these strings are recognized correctly when generating Nix expressions.

## 7. Putting It All Together

1. **Inventory Setup**
    
    - `hosts.ini` organizes the servers into relevant groups.
    - `inventory/group_vars/*.yaml` or `luxnix/autoconf/group_vars.yml` apply default or group-specific variables.
2. **Roles & Services**
    
    - Roles are toggled via variables like `some_role.enable: "true"`.
    - Additional settings for roles might appear under `host_roles` or `group_roles`.
3. **Nix / Ansible Integration**
    
    - Some roles generate Nix configuration files using Jinja templates that read the variables from these YAML files.
    - Deployment involves either running `ansible-playbook` or an automated script (e.g., `devenv run tasks autoconf:finished`) to gather facts and push the updated configurations.
4. **Authentication & SSH**
    
    - The `authentication:` section in `group_vars.yml` can store SSH public keys or references that are eventually deployed to each host or user.
    - Ansible uses these variables to create users, set up authorized keys, or configure passwordless sudo.
5. **OpenVPN / AGLNet**
    
    - `aglnet_conf` and `aglnet.client` / `aglnet.host` roles define an OpenVPN-based solution.
    - These roles are set in group or host files (e.g., `[openvpn_host] s-01`) and variables in `roles.yaml`.
    - The final system config is rendered with the correct domain, subnets, and encryption settings.


## 8. Tips & Best Practices

- **Quoting for Nix**:  
    Use double quotes inside single quotes (e.g., `'"beta"'`) to ensure the Nix config sees the string correctly.
    
- **Vault Encryption**:  
    If you store secrets in your repo, encrypt them with [Ansible Vault](https://docs.ansible.com/ansible/latest/user_guide/vault.html) to keep private keys and passwords secure.
    
- **Structured Variables**:  
    Keep variable naming consistent. For example, `group_roles`, `host_roles`, `group_luxnix`, `host_luxnix`, etc., so your templates can parse them systematically.
    
- **Development vs. Production**:  
    You can maintain separate `[under_development]` and `[main]` groups to differentiate hosts or use separate inventories (`dev`, `prod`). This helps test changes before rolling out to production.
    
- **Modular Roles**:  
    Each role (e.g., `gpu-client-dev`, `lx-anonymizer`, `aglnet.client`) should ideally exist in a standard `roles/<role_name>` structure with `tasks/main.yml`, `templates/`, `files/`, etc. This ensures clarity and maintainability.
    
