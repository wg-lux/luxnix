# Create new Entry in Ansible Inventory

- path for inventory: `ansible/inventory/hosts.ini`
- path for playbook: `ansible/site.yml`
- create host_vars: `ansible/inentory/host_vars/{hostname}.yml`
  - make sure vpn ip, kernel modules are set
    - run `sudo nixos-generate-config` on target system and check resulting hardware configuration (`/etc/nixos/hardware-configuration.nix` on target machine)
  - currently we set decryption-boot stick enable to false during setup (not sure if we crash otherwise)
- run bnsc and check resulting default.nix file
- create disks file next to host systems default.nix (see other systems for reference)
- run installer `nix run github:nix-community/nixos-anywhere -- --flake '.#xx' nixos@192.168.179.XXX`
  - e.g.: `nix run github:nix-community/nixos-anywhere -- --flake '.#s-04' nixos@192.168.0.194`
