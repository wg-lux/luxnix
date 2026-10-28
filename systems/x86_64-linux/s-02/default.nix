# s-02/default.nix

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
      roles.endoreg-client.enable = false;
    }
    {
      roles.keycloakHost.adminInitialPassword = "admin";
    }
    {
      roles.keycloakHost.adminUsername = "admin";
    }
    {
      roles.keycloakHost.dbPasswordfile = "SCRT_roles_system_password_keycloak_host_password";
    }
    {
      roles.keycloakHost.dbUsername = "keycloak";
    }
    {
      roles.keycloakHost.enable = true;
    }
    {
      roles.keycloakHost.homeDir = "/etc/keycloak";
    }
    {
      roles.nginxHost.enable = true;
    }
    {
      roles.nginxHost.glm52.enable = true;
    }
    {
      roles.nginxHost.keycloak.enable = true;
    }
    {
      roles.nginxHost.nextcloud.enable = true;
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
      roles.postgres.main.enable = true;
    }
    {
      roles.nginxHost.glm52.acme.enable = false;
    }
    {
      services.wg-lux-mcp.enable = true;
    }
    {
      services.luxnix.lxTerminology.certificateFile = "/etc/nginx-host/ssl_cert";
    }
    {
      services.luxnix.lxTerminology.certificateKeyFile = "/etc/nginx-host/ssl_key";
    }
    {
      services.luxnix.lxTerminology.domain = "terminology.endo-reg.net";
    }
    {
      services.luxnix.lxTerminology.enable = true;
    }
    {
      services.luxnix.lxTerminology.uploadTokenFile = "/run/secrets/lx-terminology-upload-token";
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
      luxnix.nvidia-prime.enable = false;
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
      luxnix.generic-settings.hostPlatform = "x86_64-linux";
    }
    {
      luxnix.generic-settings.linux.cpuMicrocode = "intel";
    }
    {
      luxnix.generic-settings.linux.initrd.availableKernelModules = [
        "xhci_pci"
        "ahci"
        "usbhid"
        "nvme"
        "usb_storage"
        "sd_mod"
      ];
    }
    {
      luxnix.generic-settings.linux.initrd.kernelModules = [
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
        "nfs"
        "btrfs"
      ];
    }
    {
      luxnix.generic-settings.systemStateVersion = "23.11";
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
  ]
