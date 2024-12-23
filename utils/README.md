# Key File Manager
For usage example see lx_admin/scripts:

## Initialize / explore identities
python scripts/init_identity.py --show
    - Creates new identity file at data/luxnix-identities.yaml
    - if exists, summarizes file

## Manage Users
python scripts/manage_user.py

Example:
### Add a user "alice" to the identity file:
python scripts/manage_user.py --add-user alice

### Add "admin@host1" role to user "alice" immediately upon creation
python scripts/manage_user.py --add-user alice --add-role admin@host1

### Remove user "bob" entirely:
python scripts/manage_user.py --remove-user bob

# Create first .sops.yaml file
python scripts/generate_sops_from_keyfilemanager.pys

# Sops Secret Manager
Potential Usage Examples

    Add a brand-new rule:

sops_mgr.add_rule(
    rule_name="dev-secrets",
    path_glob="./dev/projectA/secrets/*",
    sops_age_public_keys=["age1xxxxx", "age1yyyyy"]
)
sops_mgr.save_sops_file()

List all rules:

for i, rule in enumerate(sops_mgr.list_rules()):
    print(f"Index: {i}, Name: {rule['name']}, Glob: {rule['path_glob']}, Keys: {rule['keys']}")

Update an existing rule by index (e.g., rename it or set new keys):

sops_mgr.update_rule(
    rule_index=0, 
    new_name="my-renamed-rule",
    new_path_glob="./some/new/path/*",
    new_keys=["age1ZZZFAKE", "age1BBBFAKE"]
)
sops_mgr.save_sops_file()

Reorder rules (move the rule at index 0 to position 2):

sops_mgr.move_rule(old_index=0, new_index=2)
sops_mgr.save_sops_file()



# Create Secrets
create_secret.py

