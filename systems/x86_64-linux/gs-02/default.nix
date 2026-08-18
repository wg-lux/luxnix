# gs-02/default.nix

{
  pkgs,
  lib,
  modulesPath,
  ...
}:

lib.foldl' lib.recursiveUpdate
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
  }
  [
    { }
    {
      roles.aglnet.client.enable = true;
    }
    {
      roles.base-server.enable = true;
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
        "s-04"
      ];
    }
    {
      roles.endoreg-client.enable = true;
    }
    {
      roles.gpu-server.enable = true;
    }
    {
      roles.ssh-access.dev-01.enable = true;
    }
    {
      roles.ssh-access.dev-01.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK";
    }
    {
      roles.ssh-access.dev-03.enable = true;
    }
    {
      roles.ssh-access.dev-03.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAVt7FP3BCARMRyL791VauxIPd3t8nVm4A49VVpL9FUj";
    }
    {
      roles.ssh-access.dev-04.enable = true;
    }
    {
      roles.ssh-access.dev-04.idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICSpoZVcX+K6NdrfqcUVPTU8Ljqlp83YDzzEHjTHU2NO flippos@inexen9";
    }
    {
      roles.nginxHost.enable = true;
    }
    {
      roles.nginxHost.glm52.enable = true;
    }
    {
      roles.nginxHost.keycloak.enable = false;
    }
    {
      roles.nginxHost.nextcloud.enable = false;
    }
    {
      roles.nginxHost.settings.proxyHeadersHashBucketSize = 64;
    }
    {
      roles.nginxHost.settings.proxyHeadersHashMaxSize = 512;
    }
    {
      roles.nginxHost.settings.recommendedGzipSettings = true;
    }
    {
      roles.nginxHost.settings.recommendedOptimisation = true;
    }
    {
      roles.nginxHost.settings.recommendedProxySettings = true;
    }
    {
      roles.nginxHost.settings.recommendedTlsSettings = true;
    }
    {
      roles.nginxHost.glm52.acme.email = "hild@coloreg.de";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.celeryBroker.secureTransportConfirmed = true;
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.externalServices.redisUrl = "redis://172.16.255.14:6380/1";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.trainingWorker.cudaVisibleDevices = "0";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.trainingWorker.mode = "manual";
    }
    {
      services.luxnix.ollama.acceleration = "cuda";
    }
    {
      services.luxnix.ollama.enable = true;
    }
    {
      services.luxnix.ollama.enableModelBootstrap = false;
    }
    {
      services.luxnix.ollama.models = [ "gemma4:e2b" ];
    }
    {
      services.ollama.host = "0.0.0.0";
    }
    {
      services.luxnix.glm52.enable = true;
    }
    {
      services.luxnix.glm52.gpuLayers = 999;
    }
    {
      services.luxnix.glm52.host = "0.0.0.0";
    }
    {
      services.luxnix.glm52.port = 8088;
    }
    {
      services.luxnix.glm52.quant = "UD-IQ2_M";
    }
    {
      services.luxnix.hubStorage.hubClient.balancing.enable = false;
    }
    {
      services.luxnix.hubStorage.hubClient.balancing.residencyKey = "de";
    }
    {
      services.luxnix.hubStorage.hubClient.enable = true;
    }
    {
      services.luxnix.hubStorage.hubClient.nodes = [
        {
          identity = "gs-01";
          displayName = "gs-01 protected storage";
          failureDomain = "gs-01";
          residencyKey = "de";
          placementWeight = 100;
          artifactKinds = [
            "anonymized_video"
            "processed_report"
            "video_hls"
            "streamable_video"
            "sidecar"
            "manifest"
          ];
          endpoint = "https://gs-01.intern:9443";
          caCertificateFile = "/etc/secrets/vault/hub-storage/ca.pem";
          clientCertificateFile = "/etc/secrets/vault/hub-storage/gs-02-client.crt";
          clientKeyFile = "/etc/secrets/vault/hub-storage/gs-02-client.key";
          recipientPublicKeyFile = "/etc/secrets/vault/hub-storage/gs-01-recipient-current.pub.pem";
        }
      ];
    }
    {
      services.luxnix.lxAnnotateLocal.database.port = 5432;
    }
    {
      services.luxnix.lxAnnotateLocal.django.extraSettings."IS_CENTRAL_NODE" = lib.mkForce true;
    }
    {
      services.luxnix.lxAnnotateLocal.django.hostname = "gs-02.intern";
    }
    {
      services.luxnix.lxAnnotateLocal.django.sslCertificatePath = "/var/lib/luxnix-vault-pki/server.crt";
    }
    {
      services.luxnix.lxAnnotateLocal.django.sslKeyPath = "/var/lib/luxnix-vault-pki/server.key";
    }
    {
      services.luxnix.lxAnnotateLocal.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.backup.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.nodeProvisioning.nodes = [
        {
          nodeKey = "gc-01";
          displayName = "gc-01 site node";
          role = "site_node";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-01-source-node-secret";
        }
        {
          nodeKey = "gc-02";
          displayName = "gc-02 site node";
          role = "site_node";
          centerKey = "university_hospital_wuerzburg";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-02-source-node-secret";
        }
        {
          nodeKey = "gc-03";
          displayName = "gc-03 site node";
          role = "site_node";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-03-source-node-secret";
        }
        {
          nodeKey = "gc-04";
          displayName = "gc-04 site node";
          role = "site_node";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-04-source-node-secret";
        }
        {
          nodeKey = "gc-05";
          displayName = "gc-05 site node";
          role = "site_node";
          centerKey = "rbk_stuttgart";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-05-source-node-secret";
        }
        {
          nodeKey = "gc-06";
          displayName = "gc-06 site node";
          role = "site_node";
          centerKey = "rbk_stuttgart";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-06-source-node-secret";
        }
        {
          nodeKey = "gc-07";
          displayName = "gc-07 site node";
          role = "site_node";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-07-source-node-secret";
        }
        {
          nodeKey = "gc-08";
          displayName = "gc-08 site node";
          role = "site_node";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-08-source-node-secret";
        }
        {
          nodeKey = "gc-09";
          displayName = "gc-09 site node";
          role = "site_node";
          centerKey = "university_hospital_wuerzburg";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-09-source-node-secret";
        }
        {
          nodeKey = "gc-10";
          displayName = "gc-10 site node";
          role = "site_node";
          centerKey = "university_hospital_wuerzburg";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-10-source-node-secret";
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
      services.luxnix.lxAnnotateLocal.hub.transferApi.clientCaFile =
        "/var/lib/lx-annotate/hub-pki/client-ca.pem";
    }
    {
      services.luxnix.lxAnnotateLocal.hub.transferApi.enable = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.transferApi.mtlsMetaKey = "HTTP_X_CLIENT_CERT_VERIFIED";
    }
    {
      services.luxnix.lxAnnotateLocal.hub.transferApi.mtlsMetaValue = "SUCCESS";
    }
    {
      services.luxnix.lxAnnotateLocal.hub.transferApi.recipientPrivateKeyFiles = [
        "/etc/secrets/vault/hub-pki/hub-recipient-current.pem"
      ];
    }
    {
      services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = true;
    }
    {
      services.luxnix.lxAnnotateLocal.hub.transferApi.requireSecureTransport = true;
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.deploymentRole = "central_hub";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.externalServices.postgresHost = "127.0.0.1";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.externalServices.postgresPort = 5432;
    }
    {
      services.luxnix.lxSsl.enable = false;
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
      luxnix.generic-settings.gpu.nvidia.driver = "production";
    }
    {
      luxnix.generic-settings.gpu.nvidia.enable = true;
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
      luxnix.maintenance.autoUpdates.flake = "github:wg-lux/luxnix/prototype";
    }
    {
      luxnix.maintenance.autoUpdates.operation = "switch";
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
      luxnix.boot-decryption-stick-gs-01.enable = true;
    }
    {
      luxnix.generic-settings.hostPlatform = "x86_64-linux";
    }
    {
      luxnix.generic-settings.linux.cpuMicrocode = "amd";
    }
    {
      luxnix.generic-settings.linux.initrd.availableKernelModules = [
        "xhci_pci"
        "ahci"
        "thunderbolt"
        "nvme"
        "usb_storage"
        "usbhid"
        "sd_mod"
      ];
    }
    {
      luxnix.generic-settings.linux.initrd.kernelModules = [
        "nfs"
        "btrfs"
        "dm-snapshot"
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
        "kvm-amd"
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
        "nfs"
        "btrfs"
      ];
    }
    {
      luxnix.generic-settings.systemStateVersion = "23.11";
    }
    {
      luxnix.maintenance.autoUpdates.enable = false;
    }
    {
      luxnix.vault.server.apiAddress = "https://172.16.255.22:8200";
    }
    {
      luxnix.vault.server.bindAddress = "172.16.255.22:8200";
    }
    {
      luxnix.vault.server.caCertFile = "/var/lib/luxnix-vault-pki/ca.crt";
    }
    {
      luxnix.vault.server.clusterAddress = "https://172.16.255.22:8201";
    }
    {
      luxnix.vault.server.enable = true;
    }
    {
      luxnix.vault.server.hubPki.caCertificateFile = "/var/lib/lx-annotate/hub-pki/client-ca.pem";
    }
    {
      luxnix.vault.server.hubPki.enable = true;
    }
    {
      luxnix.vault.server.managedTls.dnsNames = [
        "vault.endo-reg.net"
        "gs-02.intern"
      ];
    }
    {
      luxnix.vault.server.managedTls.enable = true;
    }
    {
      luxnix.vault.server.managedTls.ipAddresses = [
        "172.16.255.22"
      ];
    }
    {
      luxnix.vault.server.managedTls.serverCommonName = "vault.endo-reg.net";
    }
    {
      luxnix.vault.server.tlsCertFile = "/var/lib/luxnix-vault-pki/server.crt";
    }
    {
      luxnix.vault.server.tlsKeyFile = "/var/lib/luxnix-vault-pki/server.key";
    }
    {
      hardware.nvidia.powerManagement.enable = true;
    }
    {
      hardware.nvidia.powerManagement.finegrained = false;
    }
    {
      programs.nix-ld.enable = true;
    }
    {
      xdg.menus.enable = true;
    }
    {
      networking.firewall.interfaces.tun0.allowedTCPPorts = lib.mkAfter [
        11434
        8088
        8200
      ];
    }
  ]
