# Secure Configuration Management

## Secret Files Required

The following secret files need to be created and secured appropriately:

1. **Nextcloud Admin Password**

   - Path: `/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password`
   - Content: Plain text password for the Nextcloud admin user
   - Permissions: `0600`
   - Owner: `admin:users`

2. **Minio Credentials**
   - Path: `/etc/secrets/vault/SCRT_roles_system_password_nextcloud_minio_credentials`
   - Format:
     ```
     MINIO_ROOT_USER=nextcloud
     MINIO_ROOT_PASSWORD=your_secure_password_here
     ```
   - Permissions: `0600`
   - Owner: `admin:users`

## Setting Up Secrets

You can use the following Ansible task to create these files securely:

```yaml
- name: Create nextcloud admin password
  ansible.builtin.copy:
    content: "{{ nextcloud_admin_password }}"
    dest: /etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password
    owner: root
    group: root
    mode: "0600"
  no_log: true

- name: Create minio credentials
  ansible.builtin.copy:
    content: |
      MINIO_ROOT_USER=nextcloud
      MINIO_ROOT_PASSWORD={{ minio_password }}
    dest: /etc/secrets/vault/SCRT_roles_system_password_nextcloud_minio_credentials
    owner: root
    group: root
    mode: "0600"
  no_log: true
```

## Managing Secrets with Ansible Vault

Store your sensitive variables in an encrypted file:

```yaml
# vars/secrets.yml (encrypted with ansible-vault)
nextcloud_admin_password: "secure_password_here"
minio_password: "another_secure_password_here"
```

```yaml
- name: Configure servers
  hosts: all
  vars_files:
    - vars/secrets.yml
  roles:
    - managed
```

Run your playbook with:

```bash
ansible-playbook playbook.yml --ask-vault-pass
```

## Best Practices

1. Never commit unencrypted secrets to version control
2. Rotate passwords regularly
3. Use least privilege access for secret files
4. Audit who has access to decrypt the secrets
5. Consider using a dedicated secrets management service for larger deployments
