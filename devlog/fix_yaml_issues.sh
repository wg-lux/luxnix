#!/bin/bash
# Fix missing newline at end of file
echo "" >> /home/admin/dev/luxnix/ansible/roles/deploy-files.yml
echo "" >> /home/admin/dev/luxnix/conf/check_files/conf.yaml
echo "" >> /home/admin/dev/luxnix/examples/systems/legacy/gc-06/info.yaml

# Fix extra blank lines in yml files (example for one file, repeat for others)
sed -i '/^$/d' /home/admin/dev/luxnix/conf/_nix-configs/gc-07.yml
sed -i '/^$/d' /home/admin/dev/luxnix/conf/_nix-configs/gs-01.yml
sed -i '/^$/d' /home/admin/dev/luxnix/conf/_nix-configs/gs-02.yml
sed -i '/^$/d' /home/admin/dev/luxnix/conf/_nix-configs/s-01.yml
sed -i '/^$/d' /home/admin/dev/luxnix/conf/_nix-configs/s-02.yml
sed -i '/^$/d' /home/admin/dev/luxnix/conf/_nix-configs/s-03.yml
sed -i '/^$/d' /home/admin/dev/luxnix/docs/docker-compose.yml
