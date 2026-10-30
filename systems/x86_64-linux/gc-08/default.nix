# gc-08/default.nix

{
  config,
  pkgs,
  lib,
  modulesPath,
  ...
}:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ../host-common.nix
    ./boot-decryption-config.nix
    ./disks.nix
  ];

  roles = {
    aglnet.client.enable = true;
    common.enable = true;

    custom-packages = {
      baseDevelopment = true;
      cloud = true;
      dev03 = true;
      enable = true;
      office = true;
    };

    endoreg-client = {
      api = {
        djangoAllowedHosts = [
          "localhost"
          "127.0.0.1"
          "172.16.255.106"
          "172.16.255.230"
        ];
        httpProtocol = "https";
        language = "en-us";
        logLevel = "WARNING";
        maxRequestSize = "50G";
        settingsProfile = "prod";
      };

      centralNodes = [
        "gs-02"
      ];
      enable = true;
      lxAi = true;

      paths = {
        storagePersistingEnable = true;
        storagePersistingIsExternalDrive = true;
        storagePersistingMountPoint = "/mnt/endoreg-client-storage";
      };
    };

    nextcloudClient.enable = true;
  };

  services = {
    luxnix.lxAnnotateLocal = {
      django.centerIdentitySalt = false;

      hub = {
        nodeProvisioning = {
          enable = true;
          nodes = [
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
        };

        outboundTransfer = {
          caFile = "/etc/secrets/vault/hub-pki/vault-server-ca.pem";
          enable = true;
          requireMtls = true;
        };
      };

      runtime = {
        deploymentRole = "site_node";
        ffmpegWorker.cudaVisibleDevices = "0";
        hlsEncodingProfile = "clinical_h264_nvenc_cq_v1";
        mode = "wheel";
        monitoring.enable = true;
      };
    };

    wg-lux-mcp.enable = true;
  };

  luxnix = {
    boot-decryption-stick.enable = true;
    dns.enable = true;

    generic-settings = {
      adminVpnIp = "172.16.255.106";
      enable = true;

      gpu = {
        autoDetect = true;

        nvidia = {
          driver = "production";
          enable = true;

          prime = {
            enable = true;
            nvidiaBusId = "PCI:1:0:0";
            onboardBusId = "PCI:0:2:0";
            onboardType = "intel";
          };
        };
      };

      hostPlatform = "x86_64-linux";
      language = "english";

      linux = {
        cpuMicrocode = "intel";

        initrd = {
          availableKernelModules = [
            "vmd"
            "xhci_pci"
            "ahci"
            "nvme"
            "usb_storage"
            "sd_mod"
          ];
          kernelModules = [
            "nfs"
            "btrfs"
          ];
          supportedFilesystems = [
            "nfs"
            "btrfs"
          ];
        };

        kernelModules = [
          "intel"
        ];
        kernelModulesBlacklist = [ ];
        kernelPackages = pkgs.linuxPackages_6_12;
        kernelParams = [ ];
        resumeDevice = "/dev/disk/by-label/nixos";
        supportedFilesystems = [
          "nfs"
          "btrfs"
        ];
      };

      network = {
        glm52 = {
          domain = "glm.endo-reg.net";
          port = 8088;
        };

        hosts = {
          c-01.ip-vpn = "172.16.255.131";

          gc-01 = {
            domains = [
              "gc-01.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.101";
          };

          gc-02 = {
            domains = [
              "gc-02.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.102";
          };

          gc-03 = {
            domains = [
              "gc-03.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.103";
          };

          gc-04 = {
            domains = [
              "gc-04.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.104";
          };

          gc-05 = {
            domains = [
              "gc-05.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.105";
          };

          gc-06 = {
            domains = [
              "gc-06.intern"
              "lx-annotate.local"
            ];
            ip-local = "172.31.179.8";
            ip-vpn = "172.16.255.106";
            syncthing-id = "MJU2YAF-4IXFRSS-I3JHU2Z-6LUSSTN-L6BR5HS-PLS6ACJ-4E2X2UQ-5AVBUAQ";
          };

          gc-07 = {
            domains = [
              "gc-07.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.107";
          };

          gc-08 = {
            domains = [
              "gc-08.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.108";
          };

          gc-09 = {
            domains = [
              "gc-09.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.109";
          };

          gc-10 = {
            domains = [
              "gc-10.intern"
              "lx-annotate.local"
            ];
            ip-vpn = "172.16.255.110";
          };

          gs-01 = {
            domains = [
              "gs-01.intern"
            ];
            ip-local = "192.168.0.228";
            ip-vpn = "172.16.255.21";
            network-cluster = "L2";
            syncthing-id = "X2KFB5D-HJWUNFK-GS6TP7A-GV4TGEF-ZYH3RHL-AWWJIW4-76SSCHP-YIMUUAA";
          };

          gs-02 = {
            domains = [
              "glm.endo-reg.net"
              "gs-02.intern"
              "vault.endo-reg.net"
            ];
            ip-local = "192.168.0.56";
            ip-vpn = "172.16.255.22";
            network-cluster = "L2";
            syncthing-id = "XSAKTSB-36K6OY4-NEPJ2K4-WHGZF2D-EMDOMFQ-Q5DEVO6-2BYD2MS-JWPFVQ4";
          };

          s-01 = {
            domains = [
              "s-01.intern"
            ];
            ip-local = "192.168.179.1";
            ip-vpn = "172.16.255.1";
            network-cluster = "L1";
            syncthing-id = "WTGG7YQ-AGGOG6H-PQPA54T-HQRCF4P-2T52JSI-OQTIBUG-JUCC45Y-MBCB4QS";
          };

          s-02 = {
            domains = [
              "nginx.endo-reg.net"
              "cloud.endo-reg.net"
              "keycloak.endo-reg.net"
              "s-02.intern"
            ];
            ip-local = "192.168.179.2";
            ip-vpn = "172.16.255.12";
            network-cluster = "L1";
            syncthing-id = "GF7EOBC-UVEYSV7-BK77MKA-DIK62JP-TPVG4M3-3NUUWS7-B724MAI-OK2J7AW";
          };

          s-03 = {
            domains = [
              "s-03.intern"
            ];
            ip-local = "192.168.179.3";
            ip-vpn = "172.16.255.13";
            network-cluster = "L1";
            syncthing-id = "MLC6QP7-MI5RMNB-H7JCOTE-ODXOCV7-UIIOMUS-ZRJULS7-5ZLD2LB-LYZVZAF";
          };

          s-04 = {
            domains = [
              "s-04.intern"
            ];
            ip-local = "192.168.0.194";
            ip-vpn = "172.16.255.14";
          };
        };

        keycloak = {
          adminDomain = "adminKeycloak.endo-reg.net";
          domain = "keycloak.endo-reg.net";
          port = 8443;
        };

        nextcloud.domain = "cloud.endo-reg.net";
        psqlMain.port = 5432;
        psqlTest.domain = "psql-test.endo-reg.net";

        serviceHosts = {
          glm52 = "gs-02";
          keycloak = "s-02";
          nextcloud = "s-03";
          nginx = "s-02";
          openvpn = "s-01";
          psqlMain = "gs-02";
          psqlTest = "s-04";
          redis = "s-04";
          vault = "gs-02";
        };

        syncthing = {
          enable = true;
          extraFlags = [ ];
        };
      };

      postgres.enable = true;
      sensitiveServiceGroupName = "sensitiveServices";
      smtpPwdFilePath = "/etc/secrets/vault/smtp_pwd";
      smtpUserFilePath = "/etc/secrets/vault/smtp_user";
      sslCertificateKeyPath = "/etc/secrets/vault/ssl_key";
      sslCertificatePath = "/etc/secrets/vault/ssl_cert";
      systemStateVersion = "23.11";
      traefikHostDomain = "traefik.endo-reg.net";
      traefikHostIp = "172.16.255.12";
      transferCaPath = "/var/lib/lx-annotate/ssl/transfer_ca.crt";

      virtualization = {
        enable = true;
        kvm = { };
        podman = { };
        supportedArchitectures = [ ];
        userGroups = [ ];
        vfio = { };
      };

      vpnSubnet = "172.16.255.0/24";
    };

    maintenance.autoUpdates = {
      dates = "17:00";
      enable = false;
      flake = "github:wg-lux/luxnix/prototype";
      operation = "switch";
    };

    packages.shared = [ ];

    storage.operatorUnlocked = {
      bindMounts = lib.foldl' lib.recursiveUpdate { } [
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
      enable = true;
      guardedServices = lib.id (
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

      migration = {
        accountHashes =
          lib.recursiveUpdate
            { "/var/lib/luxnix-account/admin-password.hash" = config.luxnix.vault.adminPasswordHashedFile; }
            (
              lib.optionalAttrs config.user.client.enable {
                "/var/lib/luxnix-account/client-password.hash" =
                  "${config.luxnix.vault.dir}/SCRT_client_user_password_hash";
              }
            );
        enable = true;
      };

      startupServices = lib.filter (
        name: builtins.elem "multi-user.target" config.systemd.services.${name}.wantedBy
      ) (builtins.attrNames config.luxnix.storage.operatorUnlocked.guardedServices);
      volumes =
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
    };

    vault = {
      client = {
        address = "https://vault.endo-reg.net:8200";
        allowOffline = true;

        auth = {
          deferUntilProvisioned = true;
          method = "approle";
          roleIdFile = "/etc/secrets/vault/hub-pki/approle_role_id";
          secretIdFile = "/etc/secrets/vault/hub-pki/approle_secret_id";
        };

        caCertFile = "/etc/secrets/vault/hub-pki/vault-server-ca.pem";
        hubPki.enable = true;
      };

      dir = "/etc/secrets/vault";
      enable = true;
      key = "/etc/secrets/.key";
      psk = "/etc/secrets/.psk";
    };
  };

  networking.hosts."${config.luxnix.generic-settings.network.vault.vpnIp}" = [
    "vault.endo-reg.net"
  ];

  security.luxnix.local-users = {
    adminPassword.hashedFile = "/var/lib/luxnix-account/admin-password.hash";
    clientPassword.hashedFile = "/var/lib/luxnix-account/client-password.hash";
    enable = true;
  };

  users.users.admin.extraGroups = [
    config.luxnix.generic-settings.sensitiveServiceGroupName
  ];

  xdg.menus.enable = true;
}
