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
    common.enable = true;
    custom-packages.cloud = true;
    custom-packages.enable = true;
    endoreg-client.enable = true;
    nextcloudClient.enable = true;
    postgres.default.enable = true;
    custom-packages.baseDevelopment = true;
    custom-packages.cuda = true;
    custom-packages.office = true;
    };

  services = {
    };

  luxnix = {
    boot-decryption-stick.enable = true;

dns.enable = true;

generic-settings.smtpPwdFilePath = "/etc/secrets/vault/smtp_pwd";

generic-settings.smtpUserFilePath = "/etc/secrets/vault/smtp_user";

generic-settings.sslCertificateKeyPath = "/etc/secrets/vault/ssl_key";

generic-settings.sslCertificatePath = "/etc/secrets/vault/ssl_cert";

generic-settings.adminVpnIp = "172.16.255.106";

generic-settings.configurationPathRelative = "lx-production";

generic-settings.enable = true;

generic-settings.language = "english";

generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;

generic-settings.linux.kernelParams = [];
generic-settings.network.hosts.gc-01.domains = ["gc-01.intern"];
generic-settings.network.hosts.gc-01.ip-vpn = "172.16.255.101";

generic-settings.network.hosts.gc-02.domains = ["gc-02.intern"];
generic-settings.network.hosts.gc-02.ip-vpn = "172.16.255.102";

generic-settings.network.hosts.gc-03.domains = ["gc-03.intern"];
generic-settings.network.hosts.gc-03.ip-vpn = "172.16.255.103";

generic-settings.network.hosts.gc-04.domains = ["gc-04.intern"];
generic-settings.network.hosts.gc-04.ip-vpn = "172.16.255.104";

generic-settings.network.hosts.gc-05.domains = ["gc-05.intern"];
generic-settings.network.hosts.gc-05.ip-vpn = "172.16.255.105";

generic-settings.network.hosts.gc-06.domains = ["gc-06.intern"];
generic-settings.network.hosts.gc-06.ip-local = "172.31.179.8";

generic-settings.network.hosts.gc-06.ip-vpn = "172.16.255.106";

generic-settings.network.hosts.gc-06.network-cluster = "L1";

generic-settings.network.hosts.gc-07.domains = ["gc-07.intern"];
generic-settings.network.hosts.gc-07.ip-vpn = "172.16.255.107";

generic-settings.network.hosts.gc-08.domains = ["gc-08.intern"];
generic-settings.network.hosts.gc-08.ip-vpn = "172.16.255.108";

generic-settings.network.hosts.gc-09.domains = ["gc-09.intern"];
generic-settings.network.hosts.gc-09.ip-vpn = "172.16.255.109";

generic-settings.network.hosts.gs-01.domains = ["gs-01.intern"];
generic-settings.network.hosts.gs-01.ip-local = "192.168.0.228";

generic-settings.network.hosts.gs-01.ip-vpn = "172.16.255.21";

generic-settings.network.hosts.gs-01.network-cluster = "L2";

generic-settings.network.hosts.gs-02.domains = ["gs-02.intern"];
generic-settings.network.hosts.gs-02.ip-local = "192.168.0.56";

generic-settings.network.hosts.gs-02.ip-vpn = "172.16.255.22";

generic-settings.network.hosts.gs-02.network-cluster = "L2";

generic-settings.network.hosts.s-01.domains = ["s-01.intern"];
generic-settings.network.hosts.s-01.ip-local = "192.168.179.1";

generic-settings.network.hosts.s-01.ip-vpn = "172.16.255.1";

generic-settings.network.hosts.s-01.network-cluster = "L1";

generic-settings.network.hosts.s-02.domains = ["nginx.endo-reg.net" "cloud.endo-reg.net" "keycloak.endo-reg.net" "s-02.intern"];
generic-settings.network.hosts.s-02.ip-local = "192.168.179.2";

generic-settings.network.hosts.s-02.ip-vpn = "172.16.255.12";

generic-settings.network.hosts.s-02.network-cluster = "L1";

generic-settings.network.hosts.s-03.domains = ["s-03.intern"];
generic-settings.network.hosts.s-03.ip-local = "192.168.179.3";

generic-settings.network.hosts.s-03.ip-vpn = "172.16.255.13";

generic-settings.network.hosts.s-03.network-cluster = "L1";

generic-settings.network.keycloak.adminDomain = "adminKeycloak.endo-reg.net";

generic-settings.network.keycloak.domain = "keycloak.endo-reg.net";

generic-settings.network.keycloak.port = 8443;

generic-settings.network.keycloak.vpnIp = "172.16.255.12";

generic-settings.network.nextcloud.domain = "cloud.endo-reg.net";

generic-settings.network.nextcloud.vpnIp = "172.16.255.13";

generic-settings.network.nginx.vpnIp = "172.16.255.12";

generic-settings.network.psqlMain.port = 5432;

generic-settings.network.psqlMain.vpnIp = "172.16.255.12";

generic-settings.network.psqlTest.domain = "psql-test.endo-reg.net";

generic-settings.postgres.enable = true;

generic-settings.sensitiveServiceGroupName = "sensitiveServices";

generic-settings.traefikHostDomain = "traefik.endo-reg.net";

generic-settings.traefikHostIp = "172.16.255.12";

generic-settings.vpnSubnet = "172.16.255.0/24";

gpu-eval.enable = true;

maintenance.autoUpdates.dates = "09:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "switch";

nvidia-prime.enable = true;

nvidia-prime.nvidiaDriver = "beta";

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "intel";

generic-settings.linux.initrd.availableKernelModules = ["vmd" "xhci_pci" "ahci" "nvme" "usb_storage" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "btrfs"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["intel"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.systemStateVersion = "23.11";

nvidia-prime.nvidiaBusId = "PCI:1:0:0";

nvidia-prime.onboardBusId = "PCI:0:2:0";

nvidia-prime.onboardGpuType = "intel";

};
}