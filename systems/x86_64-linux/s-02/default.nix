# /default.nix

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
    endoreg-client.enable = false;
    keycloakHost.adminInitialPassword = "admin";
    keycloakHost.adminUsername = "admin";
    keycloakHost.dbPasswordfile = "/etc/secrets/vault/SCRT_roles_system_password_keycloak_host_password";
    keycloakHost.dbUsername = "keycloak";
    keycloakHost.enable = true;
    keycloakHost.homeDir = "/home/keycloak";
    keycloakHost.hostname = "keycloak.endo-reg.net";
    keycloakHost.httpPort = 9080;
    keycloakHost.httpsPort = 9444;
    keycloakHost.vpnIP = "172.16.255.12";
    postgres.main.enable = true;
    traefikHost.allowedIPs = ["172.16.255.106" "172.16.255.1" "127.0.0.1"];    traefikHost.dashboard = true;
    traefikHost.dashboardHost = "traefik.endoreg.intern";
    traefikHost.enable = true;
    traefikHost.insecure = false;
    traefikHost.keycloak.domain = "keycloak.endo-reg.net";
    traefikHost.keycloak.enable = true;
    traefikHost.keycloak.port = 9080;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

dns.enable = true;

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.enable = true;

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.postgres.enable = true;

generic-settings.sensitiveServiceGroupName = "sensitiveServices";

generic-settings.traefikHostDomain = "traefik.endoreg.local";

generic-settings.traefikHostIp = "172.16.255.12";

maintenance.autoUpdates.dates = "04:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

nvidia-prime.enable = false;

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

generic-settings.sslCertificateKeyPath = "/etc/secrets/vault/ssl_key";

generic-settings.sslCertificatePath = "/etc/secrets/vault/ssl_cert";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "usbhid" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "btrfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.kernelParams = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.systemStateVersion = "23.11";

generic-settings.vpnIp = "172.16.255.12";

};
}