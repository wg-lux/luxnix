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

    roles = {
      aglnet.client.enable = true;
      base-server.enable = true;
      common.enable = true;

      custom-packages = {
        cloud = true;
        enable = true;
      };

      desktop.enable = true;

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
        database.port = config.services.postgresql.settings.port;
        enable = true;
        lxAi = true;
      };

      gpu-server.enable = true;

      nginxHost = {
        enable = true;
        glm52.enable = false;
        keycloak.enable = false;
        nextcloud.enable = false;

        settings = {
          proxyHeadersHashBucketSize = 64;
          proxyHeadersHashMaxSize = 512;
          recommendedGzipSettings = true;
          recommendedOptimisation = true;
          recommendedProxySettings = true;
          recommendedTlsSettings = true;
        };
      };

      ssh-access = {
        dev-01 = {
          enable = true;
          idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK";
        };

        dev-03 = {
          enable = true;
          idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAVt7FP3BCARMRyL791VauxIPd3t8nVm4A49VVpL9FUj";
        };

        dev-04 = {
          enable = true;
          idEd25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICSpoZVcX+K6NdrfqcUVPTU8Ljqlp83YDzzEHjTHU2NO flippos@inexen9";
        };
      };
    };

    services = {
      luxnix = {
        glm52 = {
          enable = true;
          host = "0.0.0.0";
          ollama.register = true;
          port = 8088;
          quant = "UD-IQ2_M";
        };

        hubStorage.hubClient = {
          balancing = {
            enable = false;
            residencyKey = "de";
          };

          enable = true;
          nodes = [
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
        };

        lxAiLocal.runtime.protectedDataDir = "/var/lib/lx-annotate/data";

        lxAnnotateLocal = {
          database = {
            host = "127.0.0.1";
            ownership = "local";
            port = config.services.postgresql.settings.port;
          };

          django = {
            enrollLegacyDefaultSalt = true;
            extraSettings."IS_CENTRAL_NODE" = lib.mkForce true;
            hostname = "gs-02.intern";
            sslCaCertificatePath = "/var/lib/luxnix-vault-pki/ca.crt";
            sslCertificatePath = "/var/lib/luxnix-vault-pki/server.crt";
            sslKeyPath = "/var/lib/luxnix-vault-pki/server.key";
          };

          enable = true;

          hub = {
            backup.enable = true;
            enable = true;

            nodeProvisioning = {
              enable = true;
              nodes = [
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
            };

            transferApi = {
              clientCaFile = "/var/lib/lx-annotate/hub-pki/client-ca.pem";
              enable = true;
              mtlsMetaKey = "HTTP_X_CLIENT_CERT_VERIFIED";
              mtlsMetaValue = "SUCCESS";
              recipientPrivateKeyFiles = [ "/etc/secrets/vault/hub-pki/hub-recipient-current.pem" ];
              requireMtls = true;
              requireSecureTransport = true;
            };
          };

          runtime = {
            celeryBroker.secureTransportConfirmed = lib.mkForce true;
            deploymentRole = "central_hub";
            externalServices.redisUrl = null;
            ffmpegWorker.cudaVisibleDevices = "0";
            hlsEncodingProfile = "clinical_h264_nvenc_cq_v1";
            llmInferenceWorker.mode = "always";
            monitoring.enable = true;

            trainingWorker = {
              cudaVisibleDevices = "0";
              mode = "manual";
            };
          };
        };

        lxSsl.enable = true;

        ollama = {
          acceleration = "cuda";
          enable = true;
          enableModelBootstrap = false;
          models = [ "gemma4:e2b" ];
        };
      };

      ollama.host = "0.0.0.0";

      redis.servers."lx-annotate" = {
        appendOnly = lib.mkForce false;
        save = lib.mkForce [ ];
        settings.dir = lib.mkForce "/run/redis-lx-annotate";
      };

      ssh.authorizedKeys = [
        "from=\"172.16.255.22\",restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHBcw5O7SQuLHz9mNyCAGFZgqQS/gUkrUfKBslRGOwX/ admin@gs-02"
      ];
      wg-lux-mcp.enable = true;
    };

    luxnix = {
      boot-decryption-stick-gs-01.enable = true;
      dns.enable = true;

      generic-settings = {
        adminVpnIp = "172.16.255.106";
        enable = true;

        gpu.nvidia = {
          driver = "stable";
          enable = true;
        };

        hostPlatform = "x86_64-linux";
        language = "english";

        linux = {
          cpuMicrocode = "amd";

          initrd = {
            availableKernelModules = [
              "xhci_pci"
              "ahci"
              "thunderbolt"
              "nvme"
              "usb_storage"
              "usbhid"
              "sd_mod"
            ];
            kernelModules = [
              "nfs"
              "btrfs"
              "dm-snapshot"
            ];
            supportedFilesystems = [
              "nfs"
              "btrfs"
            ];
          };

          kernelModules = [
            "kvm-amd"
          ];
          kernelModulesBlacklist = [ ];
          kernelPackages = pkgs.linuxPackages_6_12;
          kernelParams = [ ];
          resumeDevice = "";
          rmemMax = 7500000;
          supportedFilesystems = [
            "nfs"
            "btrfs"
          ];
          wmemMax = 7500000;
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

      nvidia-prime.enable = lib.mkForce false;
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
        dir = "/etc/secrets/vault";
        enable = true;
        key = "/etc/secrets/.key";
        psk = "/etc/secrets/.psk";

        server = {
          apiAddress = "https://${config.luxnix.generic-settings.network.vault.vpnIp}:8200";
          bindAddress = "${config.luxnix.generic-settings.network.vault.vpnIp}:8200";
          caCertFile = "/var/lib/luxnix-vault-pki/ca.crt";
          clusterAddress = "https://${config.luxnix.generic-settings.network.vault.vpnIp}:8201";
          enable = true;

          hubPki = {
            caCertificateFile = "/var/lib/lx-annotate/hub-pki/client-ca.pem";
            enable = true;
            sharedIdentityCenters = [ "university_hospital_wuerzburg" ];
          };

          managedTls = {
            dnsNames = [
              "vault.endo-reg.net"
              "gs-02.intern"
            ];
            enable = true;
            encryptedStorage = true;
            ipAddresses = [
              config.luxnix.generic-settings.network.vault.vpnIp
            ];
            serverCommonName = "vault.endo-reg.net";
          };

          tlsCertFile = "/var/lib/luxnix-vault-pki/server.crt";
          tlsKeyFile = "/var/lib/luxnix-vault-pki/server.key";
        };
      };
    };

    hardware.nvidia.powerManagement = {
      enable = true;
      finegrained = false;
    };

    networking.firewall.interfaces.tun0.allowedTCPPorts = lib.mkAfter [
      11434
      8088
      8200
    ];

    security.luxnix.local-users = {
      adminPassword.hashedFile = "/var/lib/luxnix-account/admin-password.hash";
      clientPassword.hashedFile = "/var/lib/luxnix-account/client-password.hash";
      enable = true;
    };

    swapDevices = lib.mkForce [ ];

    systemd = {
      generators.systemd-gpt-auto-generator = "/dev/null";
      services =
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

      sleep.settings.Sleep = {
        AllowHibernation = false;
        AllowHybridSleep = false;
        AllowSuspendThenHibernate = false;
      };
    };

    xdg.menus.enable = true;
  }
  [
    # Paths nested below an option set above; merged with lib.recursiveUpdate.
    {
      luxnix.storage.operatorUnlocked = {
        bindMounts = {
          "/root/vault-enrollment" = {
            volume = "luxnix-secrets";
            directory = "site-enrollment";
          };
          "/var/endoreg-service-user/lx-annotate-wheel/conf".volume = "luxnix-app-storage";
          "/var/lib/luxnix-vault-site-lifecycle" = {
            volume = "luxnix-secrets";
            directory = "site-lifecycle";
          };
        };

        volumes.luxnix-secrets = {
          container = "/var/lib/luxnix-vault-tls.luks";
          device = "/dev/mapper/luxnix-vault-pki";
          mountPoint = "/var/lib/luxnix-vault-pki";
        };
      };

      systemd.services = {
        lx-annotate-identity-salts = lib.mkIf config.luxnix.vault.server.managedTls.encryptedStorage {
          unitConfig.RequiresMountsFor = [
            "/var/lib/lx-annotate-identity-salts"
            "/var/lib/lx-annotate/data/.identity-salt-recovery"
          ];
          unitConfig.AssertPathIsMountPoint = [
            "/var/lib/lx-annotate-identity-salts"
            "/var/lib/lx-annotate/data/.identity-salt-recovery"
          ];
        };
        managed-secrets-setup = lib.mkIf config.luxnix.vault.server.managedTls.encryptedStorage {
          bindsTo = [ "etc-secrets-vault.mount" ];
          unitConfig.RequiresMountsFor = [ "/etc/secrets/vault" ];
          unitConfig.AssertPathIsMountPoint = "/etc/secrets/vault";
        };
      };
    }
  ]
