'''python
python -m compileall lx_administration/models/ansible/inventory.py


python scripts/bootstrap-lx-vault.py \
  --vault-dir ~/.lxv \
  --vault-key ~/.lxv.key \
  --inventory ./autoconf/inventory.yml \
  --local-hostname gc-06 \
  --admin-passwords ansible/secrets/admin-passwords.yml \
  --export
'''