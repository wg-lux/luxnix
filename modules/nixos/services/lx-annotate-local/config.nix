args@{ lib, ... }:
with lib;
with lib.luxnix;
with args;
let
  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-user-home
    endoreg-service-group-name;
  inherit (runtime.names) scriptName exportFramesScriptName;
  inherit (runtime.paths)
    runtimeRootPath
    repoDir
    repoStaticRootPath
    runtimeDataRootPath
    runtimeStorageRootPath
    runtimeIoImportRootPath
    runtimeStreamableVideoRootPath
    runtimeStreamableVideoRawRootPath
    runtimeStreamableVideoProcessedRootPath
    runtimeStaticRootPath
    runtimeWheelRootPath
    runtimeWheelVenvPath
    runtimeWorkingDir
    staticRootPath
    djangoStaticRootPath
    envDataDir
    envConfDir
    sslKeyPath
    sslCertPath
    hubRootPath;
  inherit (runtime.runtime)
    useWheelRuntime
    managedEncryptedDataServiceName
    encryptionServiceUnits;
  inherit (runtime.defaults)
    defaultSslCertificatePath
    defaultSslKeyPath;
  inherit (runtime.scripts.scriptNames)
    acceptanceScriptName
    celeryWorkerScriptName
    migrateVideoStreamableStorageScriptName
    watcherScriptName
    sapImportScriptName;
  inherit (runtime.scripts.packages)
    lxAnnotateBootstrapScript
    lxAnnotateEncryptedDataMountScript
    lxAnnotateEncryptedDataUmountScript
    lxAnnotateMigrateVideoStreamableStorageScript
    runLocalAcceptanceScript
    runLocalAcceptanceWheelScript
    runLocalCeleryWorkerScript
    runLocalCeleryWorkerWheelScript
    runLocalDataCleanupScript
    runLocalDataRecoveryScript
    runLocalExportFramesScript
    runLocalExportFramesWheelScript
    runLocalFileWatcherScript
    runLocalFileWatcherWheelScript
    runLocalHubBackupScript
    runLocalLxAnnotateStartScript
    runLocalLxAnnotateWheelScript
    runLocalSapImportScript
    runLocalSapImportWheelScript;
in
{
  config = mkIf cfg.enable {
    services.luxnix.lxAnnotateLocal.hub.enable =
      mkDefault (config.networking.hostName == "gs-02");
    assertions = [
      {
        assertion = cfg.runtime.mode != "wheel" || cfg.runtime.wheelPath != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.wheelPath must be set when runtime.mode = \"wheel\".";
      }
      {
        assertion =
          !lib.hasPrefix "${repoDir}/" cfg.runtime.encryptedDataDir
          && cfg.runtime.encryptedDataDir != repoDir
          && !lib.hasPrefix "${runtimeWheelRootPath}/" cfg.runtime.encryptedDataDir
          && cfg.runtime.encryptedDataDir != runtimeWheelRootPath;
        message = "services.luxnix.lxAnnotateLocal.runtime.encryptedDataDir must stay outside the repo/app path.";
      }
      {
        assertion =
          !cfg.runtime.managedEncryptedData.enable
          || cfg.runtime.managedEncryptedData.luksUuid != null
          || cfg.runtime.managedEncryptedData.luksUuidFile != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.luksUuid or luksUuidFile must be set when managedEncryptedData.enable = true.";
      }
      {
        assertion =
          !cfg.runtime.managedEncryptedData.enable
          || cfg.runtime.managedEncryptedData.keyFile != null;
        message = "services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.keyFile must be set when managedEncryptedData.enable = true.";
      }
      {
        assertion =
          !cfg.runtime.managedEncryptedData.enable
          || cfg.runtime.encryptionService == null
          || cfg.runtime.encryptionService == managedEncryptedDataServiceName;
        message = "services.luxnix.lxAnnotateLocal.runtime.encryptionService must stay unset or equal to lx-annotate-encrypted-data.service when managedEncryptedData.enable = true.";
      }
      {
        assertion =
          !cfg.runtime.vaultManagedEncryptedData.enable
          || config.networking.hostName != "";
        message = "services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData requires networking.hostName to be set.";
      }
      {
        assertion =
          !cfg.runtime.vaultManagedEncryptedData.enable
          || (
            config.luxnix.vault.enable
            && (
              config.luxnix.vault.client.auth.method != "none"
              || config.luxnix.vault.client.environmentFile != null
            )
        );
        message = "services.luxnix.lxAnnotateLocal.runtime.vaultManagedEncryptedData requires luxnix.vault client configuration, either via auth bootstrap or a declared environmentFile.";
      }
      {
        assertion =
          cfg.runtime.masterKeyFile != null
          || cfg.runtime.autoGenerateMasterKey
          || (cfg.runtime.vaultManagedEncryptedData.enable && cfg.runtime.vaultManagedEncryptedData.manageMasterKey);
        message = "services.luxnix.lxAnnotateLocal requires an application master key for encrypted storage. Set runtime.masterKeyFile, keep runtime.autoGenerateMasterKey = true, or enable vaultManagedEncryptedData.manageMasterKey.";
      }
      {
        assertion = !cfg.hub.backup.enable || cfg.hub.enable;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.enable requires services.luxnix.lxAnnotateLocal.hub.enable.";
      }
      {
        assertion = !cfg.hub.transferApi.enable || cfg.hub.enable;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.enable.";
      }
      {
        assertion =
          !cfg.hub.transferApi.enable || cfg.hub.transferApi.requireSecureTransport;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.requireSecureTransport = true.";
      }
      {
        assertion =
          !cfg.hub.transferApi.enable || cfg.hub.transferApi.requireMtls;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.requireMtls = true.";
      }
      {
        assertion =
          !cfg.hub.transferApi.enable || cfg.hub.transferApi.clientCaFile != null;
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires services.luxnix.lxAnnotateLocal.hub.transferApi.clientCaFile to be set.";
      }
      {
        assertion =
          !cfg.hub.transferApi.enable
          || (
            cfg.hub.transferApi.mtlsMetaKey != ""
            && cfg.hub.transferApi.mtlsMetaValue != ""
          );
        message = "services.luxnix.lxAnnotateLocal.hub.transferApi.enable requires non-empty mTLS meta key and value.";
      }
      {
        assertion =
          !cfg.hub.backup.enable
          || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.incomingDir;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.incomingDir must stay inside runtime.encryptedDataDir.";
      }
      {
        assertion =
          !cfg.hub.backup.enable
          || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.snapshotDir;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.snapshotDir must stay inside runtime.encryptedDataDir.";
      }
      {
        assertion =
          !cfg.hub.backup.enable
          || lib.hasPrefix "${cfg.runtime.encryptedDataDir}/" cfg.hub.backup.manifestDir;
        message = "services.luxnix.lxAnnotateLocal.hub.backup.manifestDir must stay inside runtime.encryptedDataDir.";
      }
    ];
    services.luxnix.lxAnnotateLocal.django.extraSettings.IS_CENTRAL_NODE =
      mkIf cfg.hub.enable (mkDefault true);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.enable =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable (mkDefault true);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.keyFile =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        (mkDefault cfg.runtime.vaultManagedEncryptedData.keyFilePath);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.luksUuidFile =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        (mkDefault cfg.runtime.vaultManagedEncryptedData.luksUuidFilePath);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.after =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        (mkBefore [ cfg.runtime.vaultManagedEncryptedData.setupService ]);
    services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.requires =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable
        (mkBefore [ cfg.runtime.vaultManagedEncryptedData.setupService ]);
    services.luxnix.lxAnnotateLocal.runtime.masterKeyFile = mkDefault (
      if cfg.runtime.vaultManagedEncryptedData.enable && cfg.runtime.vaultManagedEncryptedData.manageMasterKey then
        cfg.runtime.vaultManagedEncryptedData.masterKeyFilePath
      else if cfg.runtime.autoGenerateMasterKey then
        cfg.runtime.autoGeneratedMasterKeyFilePath
      else
        null
    );

    roles.managed-secrets.customSecrets.lx_annotate_master_key_local =
      mkIf (
        cfg.runtime.autoGenerateMasterKey
        && !cfg.runtime.vaultManagedEncryptedData.enable
        && (cfg.runtime.masterKeyFile == null || cfg.runtime.masterKeyFile == cfg.runtime.autoGeneratedMasterKeyFilePath)
      ) {
        path = toString cfg.runtime.autoGeneratedMasterKeyFilePath;
        owner = "root";
        group = config.luxnix.generic-settings.sensitiveServiceGroupName;
        permissions = "640";
        description = "Per-machine application master key for lx-annotate encrypted storage";
        generator = "${pkgs.openssl}/bin/openssl rand -base64 32 | tr -d '\n'";
      };

    roles.managed-secrets.customSecrets.lx_annotate_luks_key =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable {
        path = toString cfg.runtime.vaultManagedEncryptedData.keyFilePath;
        owner = "root";
        group = "root";
        permissions = "400";
        description = "Vault-backed LUKS key for lx-annotate encrypted data";
        customScript = true;
        refreshOnBoot = true;
        generator = ''
          HOSTNAME=${lib.escapeShellArg config.networking.hostName}
          VAULT_PATH=${lib.escapeShellArg (lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ] cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate)}
          ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
            | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultKeyField}' \
            > "$TARGET_FILE"
        '';
      };

    roles.managed-secrets.customSecrets.lx_annotate_luks_uuid =
      mkIf cfg.runtime.vaultManagedEncryptedData.enable {
        path = toString cfg.runtime.vaultManagedEncryptedData.luksUuidFilePath;
        owner = "root";
        group = "root";
        permissions = "400";
        description = "Vault-backed LUKS UUID for lx-annotate encrypted data";
        customScript = true;
        refreshOnBoot = true;
        generator = ''
          HOSTNAME=${lib.escapeShellArg config.networking.hostName}
          VAULT_PATH=${lib.escapeShellArg (lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ] cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate)}
          ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
            | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultUuidField}' \
            | tr -d '\n' > "$TARGET_FILE"
        '';
      };

    roles.managed-secrets.customSecrets.lx_annotate_master_key =
      mkIf (cfg.runtime.vaultManagedEncryptedData.enable && cfg.runtime.vaultManagedEncryptedData.manageMasterKey) {
        path = toString cfg.runtime.vaultManagedEncryptedData.masterKeyFilePath;
        owner = "root";
        group = config.luxnix.generic-settings.sensitiveServiceGroupName;
        permissions = "640";
        description = "Vault-backed application master key for lx-annotate encrypted storage";
        customScript = true;
        refreshOnBoot = true;
        generator = ''
          HOSTNAME=${lib.escapeShellArg config.networking.hostName}
          VAULT_PATH=${lib.escapeShellArg (lib.replaceStrings [ "{hostname}" ] [ config.networking.hostName ] cfg.runtime.vaultManagedEncryptedData.vaultPathTemplate)}
          ${pkgs.vault}/bin/vault kv get -format=json "$VAULT_PATH" \
            | ${pkgs.jq}/bin/jq -er '.data.data.${cfg.runtime.vaultManagedEncryptedData.vaultMasterKeyField}' \
            | tr -d '\n' > "$TARGET_FILE"
        '';
      };

    services.luxnix.lxAnnotateLocal.django.djangoAllowedHosts = mkAfter [
      cfg.django.hostname
    ];
    services.luxnix.lxAnnotateLocal.django.sslCertificatePath = mkDefault defaultSslCertificatePath;
    services.luxnix.lxAnnotateLocal.django.sslKeyPath = mkDefault defaultSslKeyPath;
    services.luxnix.lxSsl.enable = mkDefault true;
    services.nginx = {
      enable = true;

      recommendedProxySettings = true;
      recommendedTlsSettings = true;

      virtualHosts."${cfg.django.hostname}" = {

        forceSSL = true;
        sslCertificate = sslCertPath;
        sslCertificateKey = sslKeyPath;
        # 1. Allow massive uploads for AI Models
        extraConfig = ''
          client_max_body_size 50G;
          proxy_request_buffering off;
        ''
        + optionalString sslCfg.enable ''
          ssl_stapling off;
          ssl_stapling_verify off;
          ${optionalString cfg.hub.transferApi.enable ''
            ssl_verify_client optional;
            ssl_client_certificate ${toString cfg.hub.transferApi.clientCaFile};
          ''}
        '';
        locations."/static/" = {
          # Must match STATIC_ROOT from Step 1
          alias = "${djangoStaticRootPath}/";
          extraConfig = "expires 30d; add_header Cache-Control 'public';";
        };

        locations."/media/" = {
          # Must match MEDIA_URL env var
          alias = "${envDataDir}/";
          extraConfig = "sendfile on; tcp_nopush on;";
        };

        locations."/protected_media/" = {
          alias = "${runtimeStorageRootPath}/";
          extraConfig = "internal; sendfile on; tcp_nopush on;";
        };

        locations."/api/media/videos/" = {
          proxyPass = "http://127.0.0.1:${toString cfg.django.port}";
          proxyWebsockets = true;
          extraConfig = ''
            proxy_set_header Range $http_range;
            proxy_set_header If-Range $http_if_range;
            proxy_buffering off;
            proxy_request_buffering off;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
          '';
        };

        locations."/" = {
          proxyPass = "http://127.0.0.1:${toString cfg.django.port}";

          # 2. Critical for Streaming/WebSockets
          proxyWebsockets = true;

          # 3. Timeout tuning for long AI Inference
          extraConfig = ''
            proxy_set_header X-Client-Cert-Verified $ssl_client_verify;
            proxy_read_timeout 600s;
            proxy_send_timeout 600s;
            proxy_buffering off;
          '';
        };
      };
    };

    luxnix.generic-settings.postgres = {
      enable = true;
    };

    # Ensure directory structure exists with correct permissions
    users.users.nginx.extraGroups = [ "${endoreg-service-group-name}" ];

    systemd.tmpfiles.rules = [
      "d ${endoreg-service-user-home} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      # Important for make-based bootstrap:
      # do not pre-create ${repoDir} or repo-internal paths here. The seed clone
      # expects the checkout target to be absent (or at least empty), and creating
      # ${envDataDir}/${staticRootPath} makes it non-empty before git runs.

      # 1. The Parent Directory: systemd owns creation via StateDirectory, but
      # tmpfiles keeps permissions stable across rebuilds and restarts.
      "d /var/lib/lx-annotate 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z /var/lib/lx-annotate 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

      # 2. The SSL Directory: keep the directory permissions stable. Do not
      # mutate TLS material from nginx preStart because that path inherits the
      # nginx service sandbox and may trip seccomp or read-only mounts.
      "d /var/lib/lx-annotate/ssl 0750 root nginx - -"
      "z /var/lib/lx-annotate/ssl 0750 root nginx - -"

      # Frontend/static output lives outside the git checkout so it stays writable
      # even with systemd filesystem protections enabled.
      "d ${runtimeWheelRootPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeWheelRootPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeWheelVenvPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeWheelVenvPath} 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeDataRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeDataRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStreamableVideoRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStreamableVideoRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStreamableVideoRawRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStreamableVideoRawRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStreamableVideoProcessedRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStreamableVideoProcessedRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStorageRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStorageRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeIoImportRootPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeIoImportRootPath} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      # Desktop and service-user workflows should use this symlink as a
      # convenience access path only. It points back into the canonical
      # protected runtime import tree and is not a second IO root.
      "d ${runtimeStaticRootPath} 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${runtimeStaticRootPath}/.vite 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStaticRootPath} 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${runtimeStaticRootPath}/.vite 0775 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.dataCleanup.archiveDir} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.dataCleanup.archiveDir} 0770 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${hubRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${hubRootPath} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.hub.backup.incomingDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.hub.backup.incomingDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.hub.backup.snapshotDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.hub.backup.snapshotDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "d ${cfg.hub.backup.manifestDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
      "z ${cfg.hub.backup.manifestDir} 0750 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"

      # TLS material normalization is handled by dedicated pre-nginx services
      # such as generate-lx-ssl, not by nginx preStart.
    ]
    ++ lib.optionals (!config.roles.endoreg-client.enable) [
      # Create the config subdirectory (handled by endoreg-client role when enabled)
      "d ${endoreg-service-user-home}/config 0755 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
    ];

    systemd.services.lx-annotate-encrypted-data = mkIf cfg.runtime.managedEncryptedData.enable {
      description = "Unlock and mount encrypted data volume for lx-annotate";
      wantedBy = [ "multi-user.target" ];
      before = [ "lx-annotate-boot.service" ];
      after = [ "systemd-tmpfiles-setup.service" ] ++ cfg.runtime.managedEncryptedData.after;
      requires = cfg.runtime.managedEncryptedData.requires;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        Group = "root";
        ExecStart = "${lxAnnotateEncryptedDataMountScript}/bin/lx-annotate-encrypted-data-mount";
        ExecStop = "${lxAnnotateEncryptedDataUmountScript}/bin/lx-annotate-encrypted-data-umount";
        TimeoutStartSec = "2min";
        TimeoutStopSec = "2min";
      };
      path = [
        pkgs.coreutils
        pkgs.cryptsetup
        pkgs.util-linux
      ];
    };

    systemd.services."lx-annotate-boot" = {
      description = if useWheelRuntime then "Install lx-annotate wheel and run ASGI service" else "Clone or pull lx-annotate and run prod-server";
      wantedBy = [ "multi-user.target" ];
      wants = [
        "nginx.service"
        "postgres-endoreg-setup.service"
      ] ++ encryptionServiceUnits;
      requires = lib.optionals cfg.dataRecovery.enable [ "lx-annotate-data-recovery.service" ] ++ encryptionServiceUnits;
      after = [
        "postgres-endoreg-setup.service"
        "endoreg-django-setup.service"
        "systemd-tmpfiles-setup.service"
      ] ++ lib.optionals cfg.dataRecovery.enable [ "lx-annotate-data-recovery.service" ] ++ encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        WorkingDirectory = if useWheelRuntime then runtimeWorkingDir else endoreg-service-user-home;
        StateDirectory = "lx-annotate";
        StateDirectoryMode = "0750";
        Environment = [
          # To avoid devenv, we are passing the packages as path.
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          # This provides the missing libstdc++.so.6 and libGL.so.1
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];

        TimeoutStartSec = "5min";
        ExecStartPre = [
          "+${pkgs.writeShellScript "lx-annotate-pre-start" ''
            set -euo pipefail

            # 0. Ensure key writable directories exist with the expected owner.
            ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${endoreg-service-user-home}
            ${optionalString (!useWheelRuntime) "${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${repoDir}"}
            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
            ${pkgs.coreutils}/bin/install -d -m 0750 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envDataDir}
            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeWheelRootPath}
            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeWheelVenvPath}

            # 1b. Keep runtime static output outside the checkout and expose it at
            # ${repoStaticRootPath} is handled after checkout in the main service
            # script to avoid interfering with first-time clones.
            ${pkgs.coreutils}/bin/install -d -m 0775 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeStaticRootPath}
            ${pkgs.coreutils}/bin/install -d -m 0775 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${runtimeStaticRootPath}/.vite

            # 2. Handle the Password File securely
            SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
            TARGET_PWD="${envConfDir}/db_pwd"

            if [ -f "$SOURCE_PWD" ]; then
               echo "Copying database password..."
               cp "$SOURCE_PWD" "$TARGET_PWD"
               
               # Give ownership to the service user
               chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
               
               # Secure it
               chmod 600 "$TARGET_PWD"
            else
               echo "WARNING: Password file $SOURCE_PWD not found!"
            fi

            [ -f "${cfg.django.keycloakSecretFile}" ] && chown root:${endoreg-service-group-name} "${cfg.django.keycloakSecretFile}"
            [ -f "${cfg.django.keycloakSecretFile}" ] && chmod 640 "${cfg.django.keycloakSecretFile}"
          ''}"
        ] ++ lib.optionals (!useWheelRuntime) [
          "${lxAnnotateBootstrapScript}/bin/lx-annotate-bootstrap"
        ];
        ExecStart = if useWheelRuntime then "${runLocalLxAnnotateWheelScript}/bin/${scriptName}" else "${runLocalLxAnnotateStartScript}/bin/lx-annotate-start";
        Restart = "on-failure";
        RestartSec = "5s";
        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
        ];
        # Resource limits
        MemoryHigh = "4G";
        MemoryMax = "6G";
        CPUQuota = "50%";
        Nice = 10;
        
        # 2. Disk I/O: leave headroom for the rest of the system during startup
        IOSchedulingClass = "best-effort";
        IOSchedulingPriority = 6;

        # 3. Memory Protection
        # Prefer killing/restarting this service over killing core host processes.
        OOMScoreAdjust = 250;
      };
    };
    systemd.services.lx-annotate-data-recovery = mkIf cfg.dataRecovery.enable {
      description = "Recover legacy lx-annotate data into runtime storage";
      wantedBy = [ "multi-user.target" ];
      before = [ "lx-annotate-boot.service" ];
      wants = [ "postgresql.service" ] ++ encryptionServiceUnits;
      after = [ "systemd-tmpfiles-setup.service" "postgresql.service" ] ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = endoreg-service-user-home;
        ExecStartPre = [
          "+${pkgs.writeShellScript "lx-annotate-data-recovery-pre-start" ''
            set -euo pipefail
            SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
            TARGET_PWD="${envConfDir}/db_pwd"

            ${pkgs.coreutils}/bin/install -d -m 0755 -o ${endoreg-service-user-name} -g ${endoreg-service-group-name} ${envConfDir}
            if [ -f "$SOURCE_PWD" ]; then
              cp "$SOURCE_PWD" "$TARGET_PWD"
              chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
              chmod 600 "$TARGET_PWD"
            else
              echo "WARNING: data-recovery password file $SOURCE_PWD not found"
            fi
          ''}"
        ];
        ExecStart = "${runLocalDataRecoveryScript}/bin/runLxAnnotateDataRecovery";
        Environment = [
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          "/var/lib/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
      description = "Move duplicate anonymized lx-annotate payload into external archive storage";
      after = [
        "systemd-tmpfiles-setup.service"
        "endoreg-mount-persisting-storage.service"
      ] ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = endoreg-service-user-home;
        ExecStart = "${runLocalDataCleanupScript}/bin/runLxAnnotateDataCleanup";
        Environment = [
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          cfg.dataCleanup.archiveDir
          "/var/lib/lx-annotate"
          "/var/endoreg-service-user/lx-annotate"
          config.roles.endoreg-client.paths.storagePersistingMountPoint
        ];
      };
    };
    systemd.timers.lx-annotate-data-cleanup = mkIf cfg.dataCleanup.enable {
      description = "Periodic duplicate cleanup for anonymized lx-annotate legacy storage";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "15m";
        OnCalendar = cfg.dataCleanup.onCalendar;
        Unit = "lx-annotate-data-cleanup.service";
      };
    };
    systemd.services.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
      description = "Create protected lx-annotate hub runtime snapshots";
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = "${runLocalHubBackupScript}/bin/runLxAnnotateHubBackup";
        Environment = [
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          envDataDir
          cfg.hub.backup.incomingDir
          cfg.hub.backup.snapshotDir
          cfg.hub.backup.manifestDir
          runtimeRootPath
        ];
      };
      path = [
        pkgs.coreutils
        pkgs.findutils
        pkgs.jq
        pkgs.rsync
      ];
    };
    systemd.timers.lx-annotate-hub-backup = mkIf cfg.hub.backup.enable {
      description = "Periodic protected snapshots for the lx-annotate hub node";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "10m";
        OnCalendar = cfg.hub.backup.onCalendar;
        Unit = "lx-annotate-hub-backup.service";
      };
    };
    systemd.services.lx-annotate-filewatcher = mkIf (!useWheelRuntime || cfg.runtime.commands.fileWatcher != null) {
      description = "Django File Watcher Service";
      after = [ "postgresql.service" "lx-annotate-boot.service" ] ++ encryptionServiceUnits; # Adjust based on your DB
      wants = encryptionServiceUnits;
      requires = encryptionServiceUnits;
      wantedBy = [ "lx-annotate-boot.service" ];
      partOf = [ "lx-annotate-boot.service" ];
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };

      serviceConfig = {
        User = endoreg-service-user-name; # Or whatever user runs the app
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = if useWheelRuntime then "${runLocalFileWatcherWheelScript}/bin/${watcherScriptName}" else "${runLocalFileWatcherScript}/bin/${watcherScriptName}";
        Restart = "always";
        RestartSec = "10m";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "LX_ANNOTATE_ENCRYPTED_DATA_DIR=${runtimeDataRootPath}"
          "WATCHER_VIDEO_DIR=${runtimeDataRootPath}/videos"
          "WATCHER_REPORT_DIR=${runtimeDataRootPath}/report"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb pkgs.ffmpeg ]}"
          "DJANGO_DATA_DIR=${runtimeDataRootPath}/storage" # Fixes the storage check
        ];
        MemoryHigh = "1G";
        MemoryMax = "2G";
        CPUQuota = "35%";

        # 1. CPU Priority: Lower priority (Higher "Nice" value = nicer to others)
        Nice = 19; 

        # 2. Disk I/O Class: "idle"
        # This process will only get disk time when no other process needs it.
        # This solves the streaming stutter immediately.
        IOSchedulingClass = "idle";
        
        # 3. OOM Score: If RAM runs out, kill this service first, never the web server.
        OOMScoreAdjust = 1000;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-celery-worker = mkIf (!useWheelRuntime || cfg.runtime.commands.celeryWorker != null) {
      description = "Celery worker for asynchronous lx-annotate and endoreg-db jobs";
      after = [ "postgresql.service" "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = encryptionServiceUnits;
      wantedBy = [ "lx-annotate-boot.service" ];
      partOf = [ "lx-annotate-boot.service" ];
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };

      serviceConfig = {
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = if useWheelRuntime then "${runLocalCeleryWorkerWheelScript}/bin/${celeryWorkerScriptName}" else "${runLocalCeleryWorkerScript}/bin/${celeryWorkerScriptName}";
        Restart = "always";
        RestartSec = "15s";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        MemoryHigh = "1G";
        MemoryMax = "2G";
        CPUQuota = "35%";
        Nice = 15;
        IOSchedulingClass = "idle";
        OOMScoreAdjust = 750;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-acceptance = {
      description = "Run lx-annotate encrypted-storage and nginx acceptance checks";
      after = [ "lx-annotate-boot.service" "nginx.service" ] ++ encryptionServiceUnits;
      wants = [ "lx-annotate-boot.service" "nginx.service" ] ++ encryptionServiceUnits;
      requires = encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = if useWheelRuntime then "${runLocalAcceptanceWheelScript}/bin/${acceptanceScriptName}" else "${runLocalAcceptanceScript}/bin/${acceptanceScriptName}";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-video-streamable-migration = {
      description = "Migrate lx-annotate videos into streamable protected storage";
      wantedBy = [ "multi-user.target" ];
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      requires = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = "${lxAnnotateMigrateVideoStreamableStorageScript}/bin/${migrateVideoStreamableStorageScriptName}";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.services.lx-annotate-sap-import = {
      description = "Convert SAP IS-H zip drops into preanonymized watcher payload";
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };
      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        Group = endoreg-service-group-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = if useWheelRuntime then "${runLocalSapImportWheelScript}/bin/${sapImportScriptName}" else "${runLocalSapImportScript}/bin/${sapImportScriptName}";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.paths.lx-annotate-sap-import = {
      description = "Trigger SAP IS-H zip conversion when SAP drops exist";
      wantedBy = [ "multi-user.target" ];
      pathConfig = {
        PathExistsGlob = [ "${envDataDir}/import/sap_import/*.zip" ];
        Unit = "lx-annotate-sap-import.service";
        MakeDirectory = true;
      };
    };

    systemd.services.lx-annotate-export-frames = mkIf (!useWheelRuntime || cfg.runtime.commands.exportFrames != null) {
      description = "Export annotated frames for lx-annotate";
      after = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      wants = encryptionServiceUnits;
      requires = [ "lx-annotate-boot.service" ] ++ encryptionServiceUnits;
      unitConfig = {
        RequiresMountsFor = [ envDataDir ];
      };

      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        WorkingDirectory = runtimeWorkingDir;
        ExecStart = if useWheelRuntime then "${runLocalExportFramesWheelScript}/bin/${exportFramesScriptName}" else "${runLocalExportFramesScript}/bin/${exportFramesScriptName}";
        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
          "LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib pkgs.libglvnd pkgs.zlib pkgs.glib pkgs.libxcb ]}"
        ];
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envConfDir
          staticRootPath
          runtimeRootPath
          runtimeWheelRootPath
          runtimeWheelVenvPath
          "/var/endoreg-service-user/lx-annotate"
        ];
      };
    };
    systemd.services.nginx.serviceConfig = {
      # -5 gives Nginx slightly higher priority than standard processes
      Nice = -5;

      # Give Nginx "Best Effort" disk access, with the highest priority (0)
      # This ensures video chunks are read from disk before anything else
      IOSchedulingClass = "best-effort";
      IOSchedulingPriority = 0;
      
      # Protect Nginx from being killed if RAM runs out
      OOMScoreAdjust = -500;
    };
  };
}
