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
    common.enable = true;
    custom-packages.cloud = true;
    custom-packages.enable = true;
    endoreg-client.dbApiLocal = true;
    endoreg-client.enable = true;
    gpu-server.enable = true;
    ssh-access.dev-01.enable = true;
    ssh-access.dev-01.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK";
    ssh-access.dev-03.enable = true;
    ssh-access.dev-03.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDBJcYjGNIwOUs+KG8TbBxPWtJFEqni0p+1J5Yz++Aos";
    ssh-access.dev-04.enable = true;
    ssh-access.dev-04.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICSpoZVcX+K6NdrfqcUVPTU8Ljqlp83YDzzEHjTHU2NO flippos@inexen9";
    };

  services = {
    };

  luxnix = {
    dns.enable = true;

generic-settings.smtpPwdFilePath = "/etc/secrets/vault/smtp_pwd";

generic-settings.smtpUserFilePath = "/etc/secrets/vault/smtp_user";

generic-settings.sslCertificateKeyPath = "/etc/secrets/vault/ssl_key";

generic-settings.sslCertificatePath = "/etc/secrets/vault/ssl_cert";

generic-settings.adminVpnIp = "172.16.255.106";

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

generic-settings.network.hosts.gc-06.syncthing-id = "MJU2YAF-4IXFRSS-I3JHU2Z-6LUSSTN-L6BR5HS-PLS6ACJ-4E2X2UQ-5AVBUAQ";

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

generic-settings.network.hosts.gs-01.syncthing-id = "X2KFB5D-HJWUNFK-GS6TP7A-GV4TGEF-ZYH3RHL-AWWJIW4-76SSCHP-YIMUUAA";

generic-settings.network.hosts.gs-02.domains = ["gs-02.intern"];
generic-settings.network.hosts.gs-02.ip-local = "192.168.0.56";

generic-settings.network.hosts.gs-02.ip-vpn = "172.16.255.22";

generic-settings.network.hosts.gs-02.network-cluster = "L2";

generic-settings.network.hosts.gs-02.syncthing-id = "XSAKTSB-36K6OY4-NEPJ2K4-WHGZF2D-EMDOMFQ-Q5DEVO6-2BYD2MS-JWPFVQ4";

generic-settings.network.hosts.s-01.domains = ["s-01.intern"];
generic-settings.network.hosts.s-01.ip-local = "192.168.179.1";

generic-settings.network.hosts.s-01.ip-vpn = "172.16.255.1";

generic-settings.network.hosts.s-01.network-cluster = "L1";

generic-settings.network.hosts.s-01.syncthing-id = "WTGG7YQ-AGGOG6H-PQPA54T-HQRCF4P-2T52JSI-OQTIBUG-JUCC45Y-MBCB4QS";

generic-settings.network.hosts.s-02.domains = ["nginx.endo-reg.net" "cloud.endo-reg.net" "keycloak.endo-reg.net" "s-02.intern"];
generic-settings.network.hosts.s-02.ip-local = "192.168.179.2";

generic-settings.network.hosts.s-02.ip-vpn = "172.16.255.12";

generic-settings.network.hosts.s-02.network-cluster = "L1";

generic-settings.network.hosts.s-02.syncthing-id = "GF7EOBC-UVEYSV7-BK77MKA-DIK62JP-TPVG4M3-3NUUWS7-B724MAI-OK2J7AW";

generic-settings.network.hosts.s-03.domains = ["s-03.intern"];
generic-settings.network.hosts.s-03.ip-local = "192.168.179.3";

generic-settings.network.hosts.s-03.ip-vpn = "172.16.255.13";

generic-settings.network.hosts.s-03.network-cluster = "L1";

generic-settings.network.hosts.s-03.syncthing-id = "MLC6QP7-MI5RMNB-H7JCOTE-ODXOCV7-UIIOMUS-ZRJULS7-5ZLD2LB-LYZVZAF";

generic-settings.network.keycloak.adminDomain = "adminKeycloak.endo-reg.net";

generic-settings.network.keycloak.domain = "keycloak.endo-reg.net";

generic-settings.network.keycloak.port = 8443;

generic-settings.network.nextcloud.domain = "cloud.endo-reg.net";

generic-settings.network.psqlMain.port = 5432;

generic-settings.network.psqlTest.domain = "psql-test.endo-reg.net";

generic-settings.network.serviceHosts.keycloak = "s-02";

generic-settings.network.serviceHosts.nextcloud = "s-03";

generic-settings.network.serviceHosts.psqlMain = "gs-02";

generic-settings.network.serviceHosts.psqlTest = "s-04";

generic-settings.network.syncthing.extraFlags = [];
generic-settings.postgres.enable = true;

generic-settings.sensitiveServiceGroupName = "sensitiveServices";

generic-settings.traefikHostDomain = "traefik.endo-reg.net";

generic-settings.traefikHostIp = "172.16.255.12";

generic-settings.vpnSubnet = "172.16.255.0/24";

maintenance.autoUpdates.dates = "06:00";

maintenance.autoUpdates.enable = true;

maintenance.autoUpdates.flake = "github:wg-lux/luxnix";

maintenance.autoUpdates.operation = "switch";

nvidia-default.enable = true;

vault.dir = "/etc/secrets/vault";

vault.enable = true;

vault.key = "/etc/secrets/.key";

vault.psk = "/etc/secrets/.psk";

boot-decryption-stick-gs-01.enable = true;

generic-settings.hostPlatform = "x86_64-linux";

generic-settings.linux.cpuMicrocode = "amd";

generic-settings.linux.initrd.availableKernelModules = ["xhci_pci" "ahci" "thunderbolt" "nvme" "usb_storage" "usbhid" "sd_mod"];
generic-settings.linux.initrd.kernelModules = ["nfs" "btrfs" "dm-snapshot"];
generic-settings.linux.initrd.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.linux.kernelModules = ["kvm-amd"];
generic-settings.linux.kernelModulesBlacklist = [];
generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";

generic-settings.linux.supportedFilesystems = ["nfs" "btrfs"];
generic-settings.systemStateVersion = "23.11";

};
}