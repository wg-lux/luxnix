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
    keycloakHost.dbPasswordfile = "SCRT_roles_system_password_keycloak_host_password";
    keycloakHost.dbUsername = "keycloak";
    keycloakHost.enable = true;
    keycloakHost.homeDir = "/etc/keycloak";
    keycloakHost.hostname = "keycloak.endo-reg.net";
    keycloakHost.httpPort = 8080;
    keycloakHost.httpsPort = 8443;
    nextcloudHost.enable = true;
    nextcloudHost.hostname = "cloud.endo-reg.net";
    nextcloudHost.maxUploadSize = "10G";
    nextcloudHost.package = pkgs.nextcloud30;
    nextcloudHost.passwordFilePath = "/etc/secrets/vault/SCRT_roles_system_password_nextcloud_host_password";
    nginxHost.enable = true;
    nginxHost.keycloak.adminDomain = "keycloak-admin.endo-reg.net";
    nginxHost.keycloak.domain = "keycloak.endo-reg.net";
    nginxHost.keycloak.enable = true;
    nginxHost.nextcloud.domain = "cloud.endo-reg.net";
    nginxHost.nextcloud.enable = true;
    nginxHost.settings.proxyHeadersHashBucketSize = 64;
    nginxHost.settings.proxyHeadersHashMaxSize = 512;
    nginxHost.settings.recommendedGzipSettings = true;
    nginxHost.settings.recommendedOptimisation = true;
    nginxHost.settings.recommendedProxySettings = true;
    nginxHost.settings.recommendedTlsSettings = true;
    postgres.main.enable = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

dns.enable = true;

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.enable = true;

generic-settings.language = "english";

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.network.keycloak.port = 8443;

generic-settings.network.keycloak.vpnIp = "172.16.255.12";

generic-settings.network.nextcloud.port = 8444;

generic-settings.network.nextcloud.vpnIp = "172.16.255.12";

generic-settings.network.psql-main.port = 5432;

generic-settings.network.psql-main.vpnIp = "172.16.255.12";

generic-settings.network.psql-test.port = 5432;

generic-settings.network.psql-test.vpnIp = "172.16.255.13";

generic-settings.postgres.enable = true;

generic-settings.sensitiveServiceGroupName = "sensitiveServices";

generic-settings.traefikHostDomain = "traefik.endo-reg.net";

generic-settings.traefikHostIp = "172.16.255.12";

generic-settings.vpnSubnet = "172.16.255.0/24";

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