# Proposed Vault Refactoring

## Create Vault Model

- classmethod to initialize from ansible_inventory_dir to a target directory

  - reads inventory.yml using the Inventory model
  - initializes target directory and a lx_vault.yml file

- classmethod to create from lx_vault.yml

-

### Utility Functions

- sync inventory:
  - our Vault objects can read an existing inventory.yml and compare
  - if create_true is true we will create new non existing hosts and or secrets
  - if delete_true is true we will delete removed hosts and secrets

## Access Levels

- Align credential creation with five access levels.
- Ensure progressive disclosure based on role or environment.
