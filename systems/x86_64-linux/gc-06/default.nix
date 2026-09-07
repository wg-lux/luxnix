# gc-06/default.nix

{
  config,
  pkgs,
  lib,
  modulesPath,
  ...
}:

lib.foldl' lib.recursiveUpdate
  {
    imports = [
      (modulesPath + "/installer/scan/not-detected.nix")
      ../host-common.nix
      ./boot-decryption-config.nix
      ./disks.nix
    ];
  }
  [
    { }
    {
      roles.aglnet.client.enable = true;
    }
    {
      roles.common.enable = true;
    }
    {
      roles.custom-packages.cloud = true;
    }
    {
      roles.custom-packages.enable = true;
    }
    {
      roles.endoreg-client.api.djangoAllowedHosts = [
        "localhost"
        "127.0.0.1"
        "172.16.255.106"
        "172.16.255.230"
      ];
    }
    {
      roles.endoreg-client.api.httpProtocol = "https";
    }
    {
      roles.endoreg-client.api.language = "en-us";
    }
    {
      roles.endoreg-client.api.logLevel = "WARNING";
    }
    {
      roles.endoreg-client.api.maxRequestSize = "50G";
    }
    {
      roles.endoreg-client.api.settingsProfile = "prod";
    }
    {
      roles.endoreg-client.centralNodes = [
        "gs-02"
      ];
    }
    {
      roles.endoreg-client.enable = true;
    }
    {
      roles.endoreg-client.paths.storagePersistingEnable = true;
    }
    {
      roles.endoreg-client.paths.storagePersistingIsExternalDrive = true;
    }
    {
      roles.endoreg-client.paths.storagePersistingMountPoint = "/mnt/endoreg-client-storage";
    }
    {
      roles.nextcloudClient.enable = true;
    }
    {
      roles.custom-packages.baseDevelopment = true;
    }
    {
      roles.custom-packages.hardwareAcceleration = true;
    }
    {
      roles.custom-packages.protonmail = true;
    }
    {
      roles.custom-packages.videoEditing = true;
    }
    {
      roles.custom-packages.visuals = true;
    }
    {
      roles.endoreg-client.defaultCenterKey = "rbk_stuttgart";
    }
    {
      services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes = [
        {
          nodeKey = config.networking.hostName;
          displayName = "${config.networking.hostName} site node";
          role = "site_node";
          centerKey = config.roles.endoreg-client.defaultCenterKey;
          sharedSecretFile = "/etc/secrets/vault/hub-pki/source-node-secret";
        }
        {
          nodeKey = "gs-02";
          displayName = "gs-02 central hub";
          role = "central_hub";
          baseUrl = "https://gs-02.intern";
        }
      ];
    }
    {
      services.luxnix.lxAnnotateLocal.hub.outboundTransfer.caFile =
        "/etc/secrets/vault/hub-pki/vault-server-ca.pem";
    }
    {
      services.luxnix.lxAnnotateLocal.hub.outboundTransfer.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.outboundTransfer.requireMtls = true;
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.mode = "wheel";
    }
    {
      services.wg-lux-mcp.enable = true;
    }
    {
      luxnix.boot-decryption-stick.enable = true;
    }
    {
      luxnix.dns.enable = true;
    }
    {
      luxnix.generic-settings.smtpPwdFilePath = "/etc/secrets/vault/smtp_pwd";
    }
    {
      luxnix.generic-settings.smtpUserFilePath = "/etc/secrets/vault/smtp_user";
    }
    {
      luxnix.generic-settings.sslCertificateKeyPath = "/etc/secrets/vault/ssl_key";
    }
    {
      luxnix.generic-settings.sslCertificatePath = "/etc/secrets/vault/ssl_cert";
    }
    {
      luxnix.generic-settings.adminVpnIp = "172.16.255.106";
    }
    {
      luxnix.generic-settings.enable = true;
    }
    {
      luxnix.generic-settings.gpu.autoDetect = true;
    }
    {
      luxnix.generic-settings.gpu.nvidia.driver = "production";
    }
    {
      luxnix.generic-settings.gpu.nvidia.enable = true;
    }
    {
      luxnix.generic-settings.gpu.nvidia.prime.enable = true;
    }
    {
      luxnix.generic-settings.language = "english";
    }
    {
      luxnix.generic-settings.linux.kernelPackages = pkgs.linuxPackages_6_12;
    }
    {
      luxnix.generic-settings.linux.rmemMax = 7500000;
    }
    {
      luxnix.generic-settings.linux.wmemMax = 7500000;
    }
    {
      luxnix.generic-settings.network.glm52.domain = "glm.endo-reg.net";
    }
    {
      luxnix.generic-settings.network.glm52.port = 8088;
    }
    {
      luxnix.generic-settings.network.hosts.c-01.ip-vpn = "172.16.255.131";
    }
    {
      luxnix.generic-settings.network.hosts.gc-01.domains = [
        "gc-01.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-01.ip-vpn = "172.16.255.101";
    }
    {
      luxnix.generic-settings.network.hosts.gc-02.domains = [
        "gc-02.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-02.ip-vpn = "172.16.255.102";
    }
    {
      luxnix.generic-settings.network.hosts.gc-03.domains = [
        "gc-03.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-03.ip-vpn = "172.16.255.103";
    }
    {
      luxnix.generic-settings.network.hosts.gc-04.domains = [
        "gc-04.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-04.ip-vpn = "172.16.255.104";
    }
    {
      luxnix.generic-settings.network.hosts.gc-05.domains = [
        "gc-05.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-05.ip-vpn = "172.16.255.105";
    }
    {
      luxnix.generic-settings.network.hosts.gc-06.domains = [
        "gc-06.intern"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-06.ip-local = "172.31.179.8";
    }
    {
      luxnix.generic-settings.network.hosts.gc-06.ip-vpn = "172.16.255.106";
    }
    {
      luxnix.generic-settings.network.hosts.gc-06.syncthing-id =
        "MJU2YAF-4IXFRSS-I3JHU2Z-6LUSSTN-L6BR5HS-PLS6ACJ-4E2X2UQ-5AVBUAQ";
    }
    {
      luxnix.generic-settings.network.hosts.gc-07.domains = [
        "gc-07.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-07.ip-vpn = "172.16.255.107";
    }
    {
      luxnix.generic-settings.network.hosts.gc-08.domains = [
        "gc-08.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-08.ip-vpn = "172.16.255.108";
    }
    {
      luxnix.generic-settings.network.hosts.gc-09.domains = [
        "gc-09.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-09.ip-vpn = "172.16.255.109";
    }
    {
      luxnix.generic-settings.network.hosts.gc-10.domains = [
        "gc-10.intern"
        "lx-annotate.local"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gc-10.ip-vpn = "172.16.255.110";
    }
    {
      luxnix.generic-settings.network.hosts.gs-01.domains = [
        "gs-01.intern"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gs-01.ip-local = "192.168.0.228";
    }
    {
      luxnix.generic-settings.network.hosts.gs-01.ip-vpn = "172.16.255.21";
    }
    {
      luxnix.generic-settings.network.hosts.gs-01.network-cluster = "L2";
    }
    {
      luxnix.generic-settings.network.hosts.gs-01.syncthing-id =
        "X2KFB5D-HJWUNFK-GS6TP7A-GV4TGEF-ZYH3RHL-AWWJIW4-76SSCHP-YIMUUAA";
    }
    {
      luxnix.generic-settings.network.hosts.gs-02.domains = [
        "glm.endo-reg.net"
        "gs-02.intern"
        "vault.endo-reg.net"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.gs-02.ip-local = "192.168.0.56";
    }
    {
      luxnix.generic-settings.network.hosts.gs-02.ip-vpn = "172.16.255.22";
    }
    {
      luxnix.generic-settings.network.hosts.gs-02.network-cluster = "L2";
    }
    {
      luxnix.generic-settings.network.hosts.gs-02.syncthing-id =
        "XSAKTSB-36K6OY4-NEPJ2K4-WHGZF2D-EMDOMFQ-Q5DEVO6-2BYD2MS-JWPFVQ4";
    }
    {
      luxnix.generic-settings.network.hosts.s-01.domains = [
        "s-01.intern"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.s-01.ip-local = "192.168.179.1";
    }
    {
      luxnix.generic-settings.network.hosts.s-01.ip-vpn = "172.16.255.1";
    }
    {
      luxnix.generic-settings.network.hosts.s-01.network-cluster = "L1";
    }
    {
      luxnix.generic-settings.network.hosts.s-01.syncthing-id =
        "WTGG7YQ-AGGOG6H-PQPA54T-HQRCF4P-2T52JSI-OQTIBUG-JUCC45Y-MBCB4QS";
    }
    {
      luxnix.generic-settings.network.hosts.s-02.domains = [
        "nginx.endo-reg.net"
        "cloud.endo-reg.net"
        "keycloak.endo-reg.net"
        "s-02.intern"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.s-02.ip-local = "192.168.179.2";
    }
    {
      luxnix.generic-settings.network.hosts.s-02.ip-vpn = "172.16.255.12";
    }
    {
      luxnix.generic-settings.network.hosts.s-02.network-cluster = "L1";
    }
    {
      luxnix.generic-settings.network.hosts.s-02.syncthing-id =
        "GF7EOBC-UVEYSV7-BK77MKA-DIK62JP-TPVG4M3-3NUUWS7-B724MAI-OK2J7AW";
    }
    {
      luxnix.generic-settings.network.hosts.s-03.domains = [
        "s-03.intern"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.s-03.ip-local = "192.168.179.3";
    }
    {
      luxnix.generic-settings.network.hosts.s-03.ip-vpn = "172.16.255.13";
    }
    {
      luxnix.generic-settings.network.hosts.s-03.network-cluster = "L1";
    }
    {
      luxnix.generic-settings.network.hosts.s-03.syncthing-id =
        "MLC6QP7-MI5RMNB-H7JCOTE-ODXOCV7-UIIOMUS-ZRJULS7-5ZLD2LB-LYZVZAF";
    }
    {
      luxnix.generic-settings.network.hosts.s-04.domains = [
        "s-04.intern"
      ];
    }
    {
      luxnix.generic-settings.network.hosts.s-04.ip-local = "192.168.0.194";
    }
    {
      luxnix.generic-settings.network.hosts.s-04.ip-vpn = "172.16.255.14";
    }
    {
      luxnix.generic-settings.network.keycloak.adminDomain = "adminKeycloak.endo-reg.net";
    }
    {
      luxnix.generic-settings.network.keycloak.domain = "keycloak.endo-reg.net";
    }
    {
      luxnix.generic-settings.network.keycloak.port = 8443;
    }
    {
      luxnix.generic-settings.network.nextcloud.domain = "cloud.endo-reg.net";
    }
    {
      luxnix.generic-settings.network.psqlMain.port = 5432;
    }
    {
      luxnix.generic-settings.network.psqlTest.domain = "psql-test.endo-reg.net";
    }
    {
      luxnix.generic-settings.network.serviceHosts.glm52 = "gs-02";
    }
    {
      luxnix.generic-settings.network.serviceHosts.keycloak = "s-02";
    }
    {
      luxnix.generic-settings.network.serviceHosts.nextcloud = "s-03";
    }
    {
      luxnix.generic-settings.network.serviceHosts.nginx = "s-02";
    }
    {
      luxnix.generic-settings.network.serviceHosts.psqlMain = "gs-02";
    }
    {
      luxnix.generic-settings.network.serviceHosts.psqlTest = "s-04";
    }
    {
      luxnix.generic-settings.network.syncthing.enable = true;
    }
    {
      luxnix.generic-settings.network.syncthing.extraFlags = [ ];
    }
    {
      luxnix.generic-settings.postgres.enable = true;
    }
    {
      luxnix.generic-settings.sensitiveServiceGroupName = "sensitiveServices";
    }
    {
      luxnix.generic-settings.traefikHostDomain = "traefik.endo-reg.net";
    }
    {
      luxnix.generic-settings.traefikHostIp = "172.16.255.12";
    }
    {
      luxnix.generic-settings.transferCaPath = "/var/lib/lx-annotate/ssl/transfer_ca.crt";
    }
    {
      luxnix.generic-settings.virtualization.enable = true;
    }
    {
      luxnix.generic-settings.virtualization.kvm = { };
    }
    {
      luxnix.generic-settings.virtualization.podman = { };
    }
    {
      luxnix.generic-settings.virtualization.supportedArchitectures = [ ];
    }
    {
      luxnix.generic-settings.virtualization.userGroups = [ ];
    }
    {
      luxnix.generic-settings.virtualization.vfio = { };
    }
    {
      luxnix.generic-settings.vpnSubnet = "172.16.255.0/24";
    }
    {
      luxnix.maintenance.autoUpdates.dates = "17:00";
    }
    {
      luxnix.maintenance.autoUpdates.enable = false;
    }
    {
      luxnix.maintenance.autoUpdates.flake = "github:wg-lux/luxnix/prototype";
    }
    {
      luxnix.maintenance.autoUpdates.operation = "switch";
    }
    {
      luxnix.vault.client.address = "https://vault.endo-reg.net:8200";
    }
    {
      luxnix.vault.client.allowOffline = true;
    }
    {
      luxnix.vault.client.auth.method = "approle";
    }
    {
      luxnix.vault.client.auth.roleIdFile = "/etc/secrets/vault/hub-pki/approle_role_id";
    }
    {
      luxnix.vault.client.auth.secretIdFile = "/etc/secrets/vault/hub-pki/approle_secret_id";
    }
    {
      luxnix.vault.client.caCertFile = "/etc/secrets/vault/hub-pki/vault-server-ca.pem";
    }
    {
      luxnix.vault.client.hubPki.enable = true;
    }
    {
      luxnix.vault.dir = "/etc/secrets/vault";
    }
    {
      luxnix.vault.enable = true;
    }
    {
      luxnix.vault.key = "/etc/secrets/.key";
    }
    {
      luxnix.vault.psk = "/etc/secrets/.psk";
    }
    {
      luxnix.generic-settings.gpu.nvidia.prime.nvidiaBusId = "PCI:1:0:0";
    }
    {
      luxnix.generic-settings.gpu.nvidia.prime.onboardBusId = "PCI:0:2:0";
    }
    {
      luxnix.generic-settings.gpu.nvidia.prime.onboardType = "intel";
    }
    {
      luxnix.generic-settings.hostPlatform = "x86_64-linux";
    }
    {
      luxnix.generic-settings.linux.cpuMicrocode = "intel";
    }
    {
      luxnix.generic-settings.linux.extraModulePackages = [ ];
    }
    {
      luxnix.generic-settings.linux.initrd.availableKernelModules = [
        "vmd"
        "xhci_pci"
        "ahci"
        "nvme"
        "usb_storage"
        "sd_mod"
        "thunderbolt"
      ];
    }
    {
      luxnix.generic-settings.linux.initrd.kernelModules = [
        "dm-snapshot"
        "nfs"
        "btrfs"
      ];
    }
    {
      luxnix.generic-settings.linux.initrd.supportedFilesystems = [
        "nfs"
        "btrfs"
      ];
    }
    {
      luxnix.generic-settings.linux.kernelModules = [
        "kvm-intel"
      ];
    }
    {
      luxnix.generic-settings.linux.kernelModulesBlacklist = [ ];
    }
    {
      luxnix.generic-settings.linux.kernelParams = [ ];
    }
    {
      luxnix.generic-settings.linux.resumeDevice = "/dev/disk/by-label/nixos";
    }
    {
      luxnix.generic-settings.linux.supportedFilesystems = [
        "btrfs"
        "nfs"
      ];
    }
    {
      luxnix.generic-settings.systemStateVersion = "23.11";
    }
    {
      luxnix.gpu-eval.enable = true;
    }
    {
      luxnix.vault.client.auth.deferUntilProvisioned = true;
    }
    {
      networking.hosts."172.16.255.22" = [
        "vault.endo-reg.net"
      ];
    }
    {
      programs.nix-ld.enable = true;
    }
    {
      xdg.menus.enable = true;
    }
  ]
