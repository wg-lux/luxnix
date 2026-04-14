# nix run --extra-experimental-features 'nix-command flakes' github:nix-community/nixos-anywhere -- --flake .#h-01 --target-host root@178.104.136.182 --build-on-remote

{ config, lib, pkgs, ... }:

{
  imports =
    [
      ./hardware-configuration.nix
      ./disks.nix
    ];

  boot.loader.grub.enable = true;
  boot.initrd.availableKernelModules = [ "ahci" "xhci_pci" "virtio_pci" "virtio_scsi" "sd_mod" "sr_mod" "ext4" ];

  users.users = {
    root.hashedPassword = "!"; # Disable root login
    root.openssh.authorizedKeys.keys = [
      "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCzx1++LopfWjjt7ZQDtqBvtu89+7YsPnkC+18BV35Vt983ve2nB1ZyE0WN5Xl3jnBvZ/a+tYeWnArSh6+ywe97Jt9+YxdJRuf9F9JdiTAVKW4H9S1UwWb42rh4rM0yJoGL1dWpXRIu2e2kXDw3a4P4VYkqTeFhMSeovaLVDZ4sGCm2KkSr7SsrNs5Xydb34yOPLb7SyVd5hVYWnCqR3QEFFooShDETE83I9ThfW8JqWWpi1ApO9BJboj91pE4RwymsHcHgD4K/OP6ul/HMUPAGuJZjsgokhcb+1WK4dcTrtnRG8FHJaz2gcYL0wvIwncwPhxVLLDMXsWwxo8PO+eKJ hetzner-main"
    ];
    admin = {
      isNormalUser = true;
      extraGroups = [ "wheel" ];
      openssh.authorizedKeys.keys = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCzx1++LopfWjjt7ZQDtqBvtu89+7YsPnkC+18BV35Vt983ve2nB1ZyE0WN5Xl3jnBvZ/a+tYeWnArSh6+ywe97Jt9+YxdJRuf9F9JdiTAVKW4H9S1UwWb42rh4rM0yJoGL1dWpXRIu2e2kXDw3a4P4VYkqTeFhMSeovaLVDZ4sGCm2KkSr7SsrNs5Xydb34yOPLb7SyVd5hVYWnCqR3QEFFooShDETE83I9ThfW8JqWWpi1ApO9BJboj91pE4RwymsHcHgD4K/OP6ul/HMUPAGuJZjsgokhcb+1WK4dcTrtnRG8FHJaz2gcYL0wvIwncwPhxVLLDMXsWwxo8PO+eKJ hetzner-main"
      ];
    };
  };
nix.settings.require-sigs = false;

  # security.sudo.wheelNeedsPassword = false;

  services.openssh = {
    enable = true;
    settings = {
      PermitRootLogin = "yes";
      PasswordAuthentication = true; # false;
      KbdInteractiveAuthentication = true; # false;
    };
  };

  networking.firewall.allowedTCPPorts = [ 22 ];
  # programs.neovim = {
  #   enable = true;
  #   defaultEditor = true;
  # };

  system.stateVersion = "24.11";
}
