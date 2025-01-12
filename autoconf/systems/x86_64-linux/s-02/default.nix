# s-02/default.nix

{ config, pkgs, lib, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
  ];

  user = {
    admin = {
      name = "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

  roles = { 
    aglnet.client.enable = true;
    base-server.enable = true;
    gpu-client-dev.enable = true;
    group-all-test-group = true;
    postgres.main.authentication = ''
#type database                  DBuser                      address                     auth-method         optional_ident_map
local sameuser                  all                                                     peer                map=superuser_map
host  all                       all                172.16.255.106/32          scram-sha-256 map=superuser_map
host  replication               ${config.postgres.main.replUser}    172.16.255.106/32          scram-sha-256
host  ${config.postgres.main.devUser}            ${config.postgres.main.devUser}     172.16.255.106/32          scram-sha-256
'';
  postgres.main.enable = true;
    postgres.main.identMap = ''
# ArbitraryMapName systemUser DBUser
superuser_map      root      postgres
superuser_map      root      ${config.postgres.main.replUser}
superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
superuser_map      ${config.user.admin.name}     endoregClient
superuser_map      postgres  postgres

# Let other names login as themselves
superuser_map      /^(.*)$   \1
'';
  ssh-access.dev-01.enable = true;
    ssh-access.dev-01.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK";
    };

  services = {
    group-all-test-service = true;
    };

  luxnix = {
    generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "usbhid" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs"];
generic-settings.linux.kernelModules = ["kvm-intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelPackages = pkgs.linuxPackages_latest;

generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["btrfs"];
generic-settings.systemStateVersion = "23.11";

group-all-test-luxnix = true;

};
}