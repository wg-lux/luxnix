# How to fix long lines in YAML files

When editing the modules/nixos/secrets.yaml and modules/nixos/services/secrets.yaml files,
use YAML's folded style for long strings:

Before:
very_long_key: "this is an extremely long line that exceeds the 160 character limit and causes linting errors..."

After:
very_long_key: >-
this is an extremely long line that has been
folded into multiple lines which
makes it more readable and passes
the linting checks.

# Run this command to add an exception for these files if reformatting is not possible

echo "yaml[line-length]:" >> /home/admin/dev/luxnix/.ansible-lint-ignore
echo " - modules/nixos/secrets.yaml" >> /home/admin/dev/luxnix/.ansible-lint-ignore
echo " - modules/nixos/services/secrets.yaml" >> /home/admin/dev/luxnix/.ansible-lint-ignore
