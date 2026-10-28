# gs-02/default.nix

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
        "gs-02"
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
      roles.nginxHost.glm52.enable = false;
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
      roles.endoreg-client.database.port = config.services.postgresql.settings.port;
    }
    {
      roles.endoreg-client.lxAi = true;
    }
    {
      services.luxnix.lxAnnotateLocal.database.host = "127.0.0.1";
    }
    {
      services.luxnix.lxAnnotateLocal.database.ownership = "local";
    }
    {
      services.luxnix.lxAnnotateLocal.database.port = config.services.postgresql.settings.port;
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.celeryBroker.secureTransportConfirmed = lib.mkForce true;
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.externalServices.redisUrl = null;
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.ffmpegWorker.cudaVisibleDevices = "0";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.hlsEncodingProfile = "clinical_h264_nvenc_cq_v1";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.llmInferenceWorker.mode = "always";
    }
    {
      services.luxnix.lxAnnotateLocal.runtime.monitoring.enable = true;
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
      services.ssh.authorizedKeys = [
        "from=\"172.16.255.22\",restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHBcw5O7SQuLHz9mNyCAGFZgqQS/gUkrUfKBslRGOwX/ admin@gs-02"
      ];
    }
    {
      services.wg-lux-mcp.enable = true;
    }
    {
      services.luxnix.glm52.enable = true;
    }
    {
      services.luxnix.glm52.host = "0.0.0.0";
    }
    {
      services.luxnix.glm52.ollama.register = true;
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
      services.luxnix.lxAiLocal.runtime.protectedDataDir = "/var/lib/lx-annotate/data";
    }
    {
      services.luxnix.lxAnnotateLocal.django.enrollLegacyDefaultSalt = true;
    }
    {
      services.luxnix.lxAnnotateLocal.django.extraSettings."IS_CENTRAL_NODE" = lib.mkForce true;
    }
    {
      services.luxnix.lxAnnotateLocal.django.hostname = "gs-02.intern";
    }
    {
      services.luxnix.lxAnnotateLocal.django.sslCaCertificatePath = "/var/lib/luxnix-vault-pki/ca.crt";
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
          nodeKey = "gc-02";
          displayName = "gc-02 site node";
          role = "site_node";
          centerKey = "university_hospital_wuerzburg";
          sharedSecretFile = "/etc/secrets/vault/hub-pki/gc-02-source-node-secret";
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
          centerKey = "university_hospital_wuerzburg";
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
      services.luxnix.lxSsl.enable = true;
    }
    {
      services.redis.servers."lx-annotate".appendOnly = lib.mkForce false;
    }
    {
      services.redis.servers."lx-annotate".save = lib.mkForce [ ];
    }
    {
      services.redis.servers."lx-annotate".settings.dir = lib.mkForce "/run/redis-lx-annotate";
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
      luxnix.generic-settings.gpu.nvidia.driver = "stable";
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
        "lx-annotate.local"
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
      luxnix.generic-settings.network.serviceHosts.openvpn = "s-01";
    }
    {
      luxnix.generic-settings.network.serviceHosts.psqlMain = "gs-02";
    }
    {
      luxnix.generic-settings.network.serviceHosts.psqlTest = "s-04";
    }
    {
      luxnix.generic-settings.network.serviceHosts.redis = "s-04";
    }
    {
      luxnix.generic-settings.network.serviceHosts.vault = "gs-02";
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
      luxnix.packages.shared = [ ];
    }
    {
      luxnix.storage.operatorUnlocked.bindMounts = lib.foldl' lib.recursiveUpdate { } [
        {
          "/etc/secrets" = {
            volume = "luxnix-secrets";
            directory = "host-secrets";
          };
          "/etc/secrets/vault" = {
            volume = "luxnix-secrets";
            directory = "managed-secrets";
          };
        }
        (lib.optionalAttrs config.services.postgresql.enable {
          "/var/lib/postgresql" = {
            volume = "luxnix-app-storage";
            directory = "postgresql";
          };
        })
        (lib.optionalAttrs config.services.postgresqlBackup.enable {
          ${config.services.postgresqlBackup.location} = {
            volume = "luxnix-app-storage";
            directory = "postgresql-backups";
          };
        })
        (lib.optionalAttrs config.luxnix.vault.server.enable {
          ${config.luxnix.vault.server.storagePath} = {
            volume = "luxnix-app-storage";
            directory = "vault-data";
          };
        })
        (lib.optionalAttrs config.services.luxnix.lxAnnotateLocal.enable {
          "/var/lib/lx-annotate-identity-salts" = {
            volume = "luxnix-secrets";
            directory = "identity-salt-recovery";
          };
          "/var/lib/lx-annotate/data/.identity-salt-recovery" = {
            volume = "luxnix-secrets";
            directory = "identity-salt-replica";
          };
          "/var/endoreg-service-user/lx-annotate-wheel/conf" = {
            volume = "luxnix-secrets";
            directory = "wheel-conf";
          };
          "/var/lib/lx-annotate" = {
            volume = "luxnix-app-storage";
            directory = "application";
          };
        })
      ];
    }
    {
      luxnix.storage.operatorUnlocked.enable = true;
    }
    {
      luxnix.storage.operatorUnlocked.guardedServices = lib.id (
        let
          app = config.services.luxnix.lxAnnotateLocal;
          secrets = [
            "/etc/secrets"
            "/etc/secrets/vault"
          ];
          identity = secrets ++ [
            "/var/lib/lx-annotate-identity-salts"
            "/var/lib/lx-annotate/data/.identity-salt-recovery"
          ];
          application = [ "/var/lib/lx-annotate" ];
          database = lib.optional config.services.postgresql.enable "/var/lib/postgresql";
          workers = map (name: "lx-annotate-celery-${name}") [
            "beat"
            "worker"
            "pipeline-worker"
            "ffmpeg-worker"
            "inference-worker"
            "llm-inference-worker"
            "training-worker"
            "hub-transfer-worker"
          ];
        in
        lib.optionalAttrs (
          config.luxnix.vault.enable
          && config.luxnix.vault.client.enable
          && config.luxnix.vault.client.auth.method != "none"
        ) { vault-auth-setup = secrets; }
        // lib.optionalAttrs config.roles.managed-secrets.enable { managed-secrets-setup = secrets; }
        // lib.optionalAttrs config.services.postgresql.enable {
          postgresql = database;
          postgresql-setup = database;
        }
        // lib.optionalAttrs config.roles.postgres.default.enable { postgres-endoreg-setup = database; }
        // lib.optionalAttrs config.services.postgresqlBackup.enable (
          lib.genAttrs (
            if config.services.postgresqlBackup.backupAll then
              [ "postgresqlBackup" ]
            else
              map (name: "postgresqlBackup-${name}") config.services.postgresqlBackup.databases
          ) (_: database ++ [ config.services.postgresqlBackup.location ])
        )
        // lib.optionalAttrs config.luxnix.vault.server.enable {
          vault = secrets ++ [ config.luxnix.vault.server.storagePath ];
        }
        // lib.optionalAttrs (config.luxnix.vault.enable && config.luxnix.vault.client.hubPki.enable) {
          luxnix-vault-issue-hub-client-certificate = secrets ++ lib.optionals app.enable application;
        }
        // lib.optionalAttrs app.enable (
          {
            lx-annotate-runtime-env =
              identity ++ application ++ database ++ [ "/var/endoreg-service-user/lx-annotate-wheel/conf" ];
            lx-annotate = application;
          }
          // lib.genAttrs workers (_: application)
          // lib.optionalAttrs (!app.django.identitySaltViaSecretSpec) {
            lx-annotate-identity-salts = identity;
          }
        )
      );
    }
    {
      luxnix.storage.operatorUnlocked.migration.accountHashes =
        lib.recursiveUpdate
          { "/var/lib/luxnix-account/admin-password.hash" = config.luxnix.vault.adminPasswordHashedFile; }
          (
            lib.optionalAttrs config.user.client.enable {
              "/var/lib/luxnix-account/client-password.hash" =
                "${config.luxnix.vault.dir}/SCRT_client_user_password_hash";
            }
          );
    }
    {
      luxnix.storage.operatorUnlocked.migration.enable = true;
    }
    {
      luxnix.storage.operatorUnlocked.startupServices = lib.filter (
        name: builtins.elem "multi-user.target" config.systemd.services.${name}.wantedBy
      ) (builtins.attrNames config.luxnix.storage.operatorUnlocked.guardedServices);
    }
    {
      luxnix.storage.operatorUnlocked.volumes =
        lib.recursiveUpdate
          {
            luxnix-secrets = {
              mountPoint = "/var/lib/luxnix-secrets";
              container = "/var/lib/luxnix-secrets.luks";
              minimumSizeMiB = 256;
              noexec = true;
            };
          }
          (
            lib.optionalAttrs
              (
                config.services.luxnix.lxAnnotateLocal.enable
                || config.services.postgresql.enable
                || config.luxnix.vault.server.enable
              )
              {
                luxnix-app-storage = {
                  mountPoint = "/var/lib/luxnix-app-storage";
                  container = "/var/lib/luxnix-app-storage.luks";
                };
              }
          );
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
      luxnix.generic-settings.linux.resumeDevice = "";
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
      luxnix.nvidia-prime.enable = lib.mkForce false;
    }
    {
      luxnix.storage.operatorUnlocked.bindMounts."/root/vault-enrollment" = {
        volume = "luxnix-secrets";
        directory = "site-enrollment";
      };
    }
    {
      luxnix.storage.operatorUnlocked.bindMounts."/var/endoreg-service-user/lx-annotate-wheel/conf".volume =
        "luxnix-app-storage";
    }
    {
      luxnix.storage.operatorUnlocked.bindMounts."/var/lib/luxnix-vault-site-lifecycle" = {
        volume = "luxnix-secrets";
        directory = "site-lifecycle";
      };
    }
    {
      luxnix.storage.operatorUnlocked.volumes.luxnix-secrets.container = "/var/lib/luxnix-vault-tls.luks";
    }
    {
      luxnix.storage.operatorUnlocked.volumes.luxnix-secrets.device = "/dev/mapper/luxnix-vault-pki";
    }
    {
      luxnix.storage.operatorUnlocked.volumes.luxnix-secrets.mountPoint = "/var/lib/luxnix-vault-pki";
    }
    {
      luxnix.vault.server.apiAddress = "https://${config.luxnix.generic-settings.network.vault.vpnIp}:8200";
    }
    {
      luxnix.vault.server.bindAddress = "${config.luxnix.generic-settings.network.vault.vpnIp}:8200";
    }
    {
      luxnix.vault.server.caCertFile = "/var/lib/luxnix-vault-pki/ca.crt";
    }
    {
      luxnix.vault.server.clusterAddress = "https://${config.luxnix.generic-settings.network.vault.vpnIp}:8201";
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
      luxnix.vault.server.hubPki.sharedIdentityCenters = [ "university_hospital_wuerzburg" ];
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
      luxnix.vault.server.managedTls.encryptedStorage = true;
    }
    {
      luxnix.vault.server.managedTls.ipAddresses = [
        config.luxnix.generic-settings.network.vault.vpnIp
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
      security.luxnix.local-users.adminPassword.hashedFile =
        "/var/lib/luxnix-account/admin-password.hash";
    }
    {
      security.luxnix.local-users.clientPassword.hashedFile =
        "/var/lib/luxnix-account/client-password.hash";
    }
    {
      security.luxnix.local-users.enable = true;
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
    {
      swapDevices = lib.mkForce [ ];
    }
    {
      systemd.generators.systemd-gpt-auto-generator = "/dev/null";
    }
    {
      systemd.services =
        lib.genAttrs [ "lx-annotate-runtime-env" "postgresql" "postgresql-setup" "postgres-endoreg-setup" ]
          (_: {
            bindsTo = [
              "var-lib-lx\\x2dannotate.mount"
              "var-lib-postgresql.mount"
              "var-endoreg\\x2dservice\\x2duser-lx\\x2dannotate\\x2dwheel-conf.mount"
            ];
            unitConfig.RequiresMountsFor = [
              "/var/lib/lx-annotate"
              "/var/lib/postgresql"
              "/var/endoreg-service-user/lx-annotate-wheel/conf"
            ];
            unitConfig.AssertPathIsMountPoint = [
              "/var/lib/lx-annotate"
              "/var/lib/postgresql"
              "/var/endoreg-service-user/lx-annotate-wheel/conf"
            ];
          });
    }
    {
      systemd.services.lx-annotate-identity-salts =
        lib.mkIf config.luxnix.vault.server.managedTls.encryptedStorage
          {
            unitConfig.RequiresMountsFor = [
              "/var/lib/lx-annotate-identity-salts"
              "/var/lib/lx-annotate/data/.identity-salt-recovery"
            ];
            unitConfig.AssertPathIsMountPoint = [
              "/var/lib/lx-annotate-identity-salts"
              "/var/lib/lx-annotate/data/.identity-salt-recovery"
            ];
          };
    }
    {
      systemd.services.managed-secrets-setup =
        lib.mkIf config.luxnix.vault.server.managedTls.encryptedStorage
          {
            bindsTo = [ "etc-secrets-vault.mount" ];
            unitConfig.RequiresMountsFor = [ "/etc/secrets/vault" ];
            unitConfig.AssertPathIsMountPoint = "/etc/secrets/vault";
          };
    }
    {
      systemd.sleep.settings.Sleep.AllowHibernation = false;
    }
    {
      systemd.sleep.settings.Sleep.AllowHybridSleep = false;
    }
    {
      systemd.sleep.settings.Sleep.AllowSuspendThenHibernate = false;
    }
  ]
