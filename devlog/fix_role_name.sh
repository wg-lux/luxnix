#!/bin/bash
# Run this script to rename the role
mv /home/admin/dev/luxnix/ansible/roles/lx-anonymizer /home/admin/dev/luxnix/ansible/roles/lx_anonymizer

# Update any references to the role in playbooks and inventory files
find /home/admin/dev/luxnix -type f -name "*.yml" -exec sed -i 's/lx-anonymizer/lx_anonymizer/g' {} \;
