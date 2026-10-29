# Value of the module config: units, files and assertions built from the tools.
{
  lib,
  pkgs,
  config,
  ctx,
  ...
}:
with lib;
with lib.luxnix;
let
  inherit (ctx)
    cfg
    runtimeDir
    vaultAuthEnabled
    verifySecretStorage
    serverCfg
    serverWaitsForBindAddress
    serverVpnServices
    managedTlsCfg
    tlsStorageMountUnit
    hubPkiCfg
    clientHubPkiCfg
    clientHubPkiSecretDirectories
    vaultAuthProvisioningConditionScript
    vaultEnrollmentStatusTool
    vaultAuthCleanupScript
    waitForServerBindAddress
    serverRebuildPreparationTool
    managedServerTlsCommand
    hubPkiBootstrapTool
    publishHubClientCaScript
    hubSitesReconcileTool
    oidcClientSecretPublishTool
    hubSiteLifecycleTool
    hubSiteEnrollmentTool
    vaultCaInstallTool
    hubSiteEnrollmentInstallTool
    forceHubClientReissueTool
    issueHubClientCertificateScript
    ;
in
mkIf cfg.enable {
  assertions = [
    {
      assertion = !vaultAuthEnabled || cfg.client.address != null || cfg.client.environmentFile != null;
      message = "luxnix.vault.client.address or luxnix.vault.client.environmentFile must be set when Vault auth bootstrap is enabled.";
    }
    {
      assertion = cfg.client.auth.method != "tokenFile" || cfg.client.auth.tokenFile != null;
      message = "luxnix.vault.client.auth.tokenFile must be set when auth.method = \"tokenFile\".";
    }
    {
      assertion =
        cfg.client.auth.method != "approle"
        || (cfg.client.auth.roleIdFile != null && cfg.client.auth.secretIdFile != null);
      message = "luxnix.vault.client.auth.roleIdFile and secretIdFile must be set when auth.method = \"approle\".";
    }
    {
      assertion =
        !cfg.client.auth.deferUntilProvisioned
        || (
          cfg.client.auth.method == "approle"
          && cfg.client.auth.roleIdFile != null
          && cfg.client.auth.secretIdFile != null
          && cfg.client.caCertFile != null
        );
      message = "luxnix.vault.client.auth.deferUntilProvisioned requires AppRole authentication files and a Vault CA certificate file.";
    }
    {
      assertion =
        !serverCfg.enable
        || !((config.luxnix.generic-settings.network.serviceHosts or { }) ? vault)
        || config.luxnix.generic-settings.network.serviceHosts.vault == config.networking.hostName;
      message = "An inventory-managed Vault server must run on network.serviceHosts.vault; move its server configuration with the host selection.";
    }
    {
      assertion = !serverCfg.enable || (serverCfg.tlsCertFile != null && serverCfg.tlsKeyFile != null);
      message = "luxnix.vault.server.enable requires runtime TLS certificate and key files.";
    }
    {
      assertion = !managedTlsCfg.encryptedStorage || (serverCfg.enable && managedTlsCfg.enable);
      message = "Encrypted Vault TLS storage requires the Vault server and managed TLS.";
    }
    {
      assertion =
        !managedTlsCfg.enable
        || (
          serverCfg.enable
          && serverCfg.caCertFile != null
          && serverCfg.tlsCertFile != null
          && serverCfg.tlsKeyFile != null
          && serverCfg.caCertFile != serverCfg.tlsCertFile
          && managedTlsCfg.dnsNames != [ ]
        );
      message = "luxnix.vault.server.managedTls requires Vault, distinct CA/leaf paths, and at least one DNS SAN.";
    }
    {
      assertion =
        !managedTlsCfg.enable
        || lib.all (path: builtins.dirOf path == managedTlsCfg.stateDirectory) [
          (toString serverCfg.caCertFile)
          managedTlsCfg.caKeyFile
          (toString serverCfg.tlsCertFile)
          (toString serverCfg.tlsKeyFile)
        ];
      message = "Managed Vault CA and server-leaf files must share managedTls.stateDirectory.";
    }
    {
      assertion =
        !managedTlsCfg.enable
        || (
          managedTlsCfg.leafValidityDays > managedTlsCfg.renewBeforeDays
          && managedTlsCfg.caValidityDays > managedTlsCfg.renewBeforeDays
          && lib.elem managedTlsCfg.serverCommonName managedTlsCfg.dnsNames
        );
      message = "Managed Vault TLS validity must exceed its renewal window, and the server common name must be a DNS SAN.";
    }
    {
      assertion = !serverCfg.enable || lib.hasPrefix "https://" serverCfg.apiAddress;
      message = "luxnix.vault.server.apiAddress must use https://.";
    }
    {
      assertion = !hubPkiCfg.enable || serverCfg.enable;
      message = "luxnix.vault.server.hubPki.enable requires the Vault server.";
    }
    {
      assertion = !hubPkiCfg.enable || serverCfg.caCertFile != null;
      message = "luxnix.vault.server.hubPki.enable requires the stable Vault server CA file.";
    }
    {
      assertion = !clientHubPkiCfg.enable || vaultAuthEnabled;
      message = "luxnix.vault.client.hubPki.enable requires tokenFile or AppRole Vault authentication.";
    }
    {
      assertion =
        !clientHubPkiCfg.enable
        || cfg.client.auth.method != "approle"
        ||
          lib.all
            (
              path:
              path == null || builtins.dirOf (toString path) == builtins.dirOf clientHubPkiCfg.nodeSecretFile
            )
            [
              cfg.client.auth.roleIdFile
              cfg.client.auth.secretIdFile
              cfg.client.caCertFile
              clientHubPkiCfg.recipientPublicKeyFile
            ];
      message = "AppRole hub-site enrollment files and the recipient public key must share the node-secret directory.";
    }
    {
      assertion =
        !clientHubPkiCfg.enable
        || (
          let
            certificateDir = builtins.dirOf clientHubPkiCfg.certificateFile;
          in
          builtins.dirOf clientHubPkiCfg.keyFile == certificateDir
          && builtins.dirOf clientHubPkiCfg.caCertificateFile == certificateDir
        );
      message = "Vault hub client certificate, key, and CA files must share one protected runtime directory.";
    }
  ];

  services.vault = lib.mkIf serverCfg.enable {
    enable = true;
    address = serverCfg.bindAddress;
    tlsCertFile = toString serverCfg.tlsCertFile;
    tlsKeyFile = toString serverCfg.tlsKeyFile;
    storageBackend = "raft";
    inherit (serverCfg) storagePath;
    storageConfig = ''
      node_id = ${builtins.toJSON serverCfg.nodeId}
    '';
    extraConfig = ''
      api_addr = ${builtins.toJSON serverCfg.apiAddress}
      cluster_addr = ${builtins.toJSON serverCfg.clusterAddress}
      ui = false
      disable_mlock = false
    '';
  };

  users.users = lib.optionalAttrs serverCfg.enable {
    vault.extraGroups = [
      config.luxnix.generic-settings.sensitiveServiceGroupName
    ]
    ++ lib.optional config.services.nginx.enable "nginx";
  };

  roles.managed-secrets.customSecrets.lx_hub_source_node_secret =
    lib.mkIf (clientHubPkiCfg.enable && !cfg.client.auth.deferUntilProvisioned)
      {
        path = clientHubPkiCfg.nodeSecretFile;
        owner = "root";
        group = config.luxnix.generic-settings.sensitiveServiceGroupName;
        permissions = "640";
        description = "Vault-backed LX-Annotate NetworkNode request-authentication secret";
        customScript = true;
        refreshOnBoot = true;
        generator = ''
          ${pkgs.vault}/bin/vault kv get -field=shared_secret \
            ${lib.escapeShellArg "${clientHubPkiCfg.kvMountPath}/nodes/${clientHubPkiCfg.commonName}"} \
            | ${pkgs.coreutils}/bin/tr -d '\n' > "$TARGET_FILE"
          if [ ! -s "$TARGET_FILE" ]; then
            echo "ERROR: Vault returned an empty hub source-node secret." >&2
            exit 1
          fi
        '';
      };

  roles.managed-secrets.customSecrets.lx_hub_recipient_public_key =
    lib.mkIf (clientHubPkiCfg.enable && !cfg.client.auth.deferUntilProvisioned)
      {
        path = clientHubPkiCfg.recipientPublicKeyFile;
        owner = "root";
        group = config.luxnix.generic-settings.sensitiveServiceGroupName;
        permissions = "640";
        description = "Vault-authenticated central-hub X25519 envelope recipient public key";
        customScript = true;
        refreshOnBoot = true;
        generator = ''
          ${pkgs.vault}/bin/vault kv get -field=public_key \
            ${lib.escapeShellArg "${clientHubPkiCfg.kvMountPath}/${clientHubPkiCfg.recipientPublicKeyKvPath}"} \
            > "$TARGET_FILE"
          if [ ! -s "$TARGET_FILE" ] \
            || ! ${pkgs.openssl}/bin/openssl pkey -pubin -in "$TARGET_FILE" -text_pub -noout 2>/dev/null \
              | ${pkgs.gnugrep}/bin/grep -q X25519; then
            echo "ERROR: Vault returned an invalid central-hub X25519 recipient public key." >&2
            exit 1
          fi
        '';
      };

  environment.systemPackages =
    lib.optionals hubPkiCfg.enable [
      hubPkiBootstrapTool
      hubSitesReconcileTool
      hubSiteEnrollmentTool
      oidcClientSecretPublishTool
      serverRebuildPreparationTool
      hubSiteLifecycleTool
      pkgs.vault
    ]
    ++ lib.optionals (cfg.client.enable && cfg.client.caCertFile != null) [
      vaultCaInstallTool
    ]
    ++ lib.optionals managedTlsCfg.encryptedStorage [ pkgs.cryptsetup ]
    ++ lib.optionals clientHubPkiCfg.enable [ forceHubClientReissueTool ]
    ++ lib.optionals (clientHubPkiCfg.enable && cfg.client.auth.method == "approle") [
      hubSiteEnrollmentInstallTool
    ]
    ++ lib.optionals vaultAuthEnabled [
      vaultEnrollmentStatusTool
    ];

  fileSystems = lib.mkIf managedTlsCfg.encryptedStorage {
    ${managedTlsCfg.stateDirectory} = {
      device = "/dev/mapper/luxnix-vault-pki";
      fsType = "ext4";
      # Unlock is an operator action after SSH is available, never a Vault client dependency.
      options = [
        "noauto"
        "nodev"
        "nosuid"
        "noexec"
        "x-systemd.device-timeout=10s"
      ];
    };
  };

  systemd = {
    services = {
      vault = lib.mkIf serverCfg.enable {
        bindsTo = lib.optional managedTlsCfg.encryptedStorage tlsStorageMountUnit;
        unitConfig.RequiresMountsFor = lib.optional managedTlsCfg.encryptedStorage managedTlsCfg.stateDirectory;
        unitConfig.AssertPathIsMountPoint = lib.mkIf managedTlsCfg.encryptedStorage managedTlsCfg.stateDirectory;
        after = [
          "managed-secrets-setup.service"
          "network-online.target"
        ]
        ++ serverVpnServices
        ++ lib.optional (
          config.services.luxnix.lxSsl.enable && !managedTlsCfg.enable
        ) "generate-lx-ssl.service";
        # Soft ordering only: a VPN restart must not stop (and thereby seal) Vault.
        wants = [
          "managed-secrets-setup.service"
          "network-online.target"
        ]
        ++ serverVpnServices;
        requires = lib.optional (
          config.services.luxnix.lxSsl.enable && !managedTlsCfg.enable
        ) "generate-lx-ssl.service";
        # The whole fleet depends on this server: never give up restarting it.
        startLimitIntervalSec = lib.mkForce 0;
        serviceConfig = {
          # "+" runs the address probe with full privileges; Vault stays unprivileged.
          ExecStartPre = lib.optional serverWaitsForBindAddress "+${waitForServerBindAddress}";
          TimeoutStartSec = "3min";
          Restart = lib.mkForce "always";
          RestartSec = "5s";
          RestartSteps = 5;
          RestartMaxDelaySec = "1min";
        };
      };

      luxnix-vault-managed-server-tls = lib.mkIf managedTlsCfg.enable {
        description = "Maintain the CA-signed Vault server leaf without rotating its CA";
        bindsTo = lib.optional managedTlsCfg.encryptedStorage tlsStorageMountUnit;
        unitConfig.RequiresMountsFor = lib.optional managedTlsCfg.encryptedStorage managedTlsCfg.stateDirectory;
        unitConfig.AssertPathIsMountPoint = lib.mkIf managedTlsCfg.encryptedStorage managedTlsCfg.stateDirectory;
        before = [ "vault.service" ] ++ lib.optional config.services.nginx.enable "nginx.service";
        requiredBy = [ "vault.service" ] ++ lib.optional config.services.nginx.enable "nginx.service";
        after = [ "systemd-tmpfiles-setup.service" ];
        requires = [ "systemd-tmpfiles-setup.service" ];
        serviceConfig = {
          Type = "oneshot";
          ExecStartPre =
            "${verifySecretStorage} "
            + lib.escapeShellArgs [
              managedTlsCfg.stateDirectory
              managedTlsCfg.caKeyFile
              (toString serverCfg.tlsKeyFile)
            ];
          LimitCORE = 0;
          ExecStart = managedServerTlsCommand;
          ExecStartPost = pkgs.writeShellScript "reload-vault-after-leaf-rotation" ''
            marker=${lib.escapeShellArg "${runtimeDir}/server-leaf-rotated"}
            if [ -e "$marker" ] && ${pkgs.systemd}/bin/systemctl is-active --quiet vault.service; then
              # Vault reloads listener certificate/key file contents on SIGHUP.
              ${pkgs.systemd}/bin/systemctl kill --kill-whom=main --signal=HUP vault.service
            fi
            if [ -e "$marker" ] && ${pkgs.systemd}/bin/systemctl is-active --quiet nginx.service; then
              ${pkgs.systemd}/bin/systemctl reload nginx.service
            fi
          '';
          UMask = "0077";
        };
      };

    };

    timers.luxnix-vault-managed-server-tls = lib.mkIf managedTlsCfg.enable {
      description = "Check whether the Vault server leaf needs renewal";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "5m";
        OnUnitActiveSec = "12h";
        RandomizedDelaySec = "30m";
        Persistent = true;
        Unit = "luxnix-vault-managed-server-tls.service";
      };
    };

    services.luxnix-vault-issue-hub-client-certificate = lib.mkIf clientHubPkiCfg.enable {
      description = "Issue or renew the LX-Annotate hub-transfer client certificate";
      path = [
        pkgs.vault
        pkgs.jq
        pkgs.getent
      ];
      wantedBy = lib.optionals (!cfg.client.auth.deferUntilProvisioned) [ "multi-user.target" ];
      before = [ "lx-annotate-celery-hub-transfer-worker.service" ];
      after = [
        "vault-auth-setup.service"
        "network-online.target"
      ];
      requires = [ "vault-auth-setup.service" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        LimitCORE = 0;
        ExecStart = issueHubClientCertificateScript;
        Environment = lib.optionals cfg.client.allowOffline [
          "VAULT_CLIENT_TIMEOUT=5s"
        ];
        EnvironmentFile = "-${cfg.client.runtimeEnvironmentFile}";
        UMask = "0077";
      };
    };

    timers.luxnix-vault-issue-hub-client-certificate = lib.mkIf clientHubPkiCfg.enable {
      description = "Renew the LX-Annotate hub-transfer client certificate";
      wantedBy = lib.optionals (!cfg.client.auth.deferUntilProvisioned) [ "timers.target" ];
      timerConfig = {
        OnBootSec = "2m";
        OnUnitActiveSec = "12h";
        RandomizedDelaySec = "15m";
        Persistent = true;
        Unit = "luxnix-vault-issue-hub-client-certificate.service";
      };
    };

    services.luxnix-vault-publish-hub-client-ca = lib.mkIf hubPkiCfg.enable {
      description = "Atomically publish the Vault hub-transfer client CA";
      wantedBy = [ "multi-user.target" ];
      before = [ "nginx.service" ];
      after = [
        "vault.service"
        "network-online.target"
      ];
      requires = [ "vault.service" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        TimeoutStartSec = "4min";
        ExecStart = publishHubClientCaScript;
        Restart = "on-failure";
        RestartSec = "5s";
        UMask = "0027";
      };
    };

    tmpfiles.rules = [
      "d ${runtimeDir} 0700 root root - -"
      "z ${runtimeDir} 0700 root root - -"
    ]
    ++ lib.optionals clientHubPkiCfg.enable (
      map (
        directory:
        "d ${directory} 0750 root ${config.luxnix.generic-settings.sensitiveServiceGroupName} - -"
      ) clientHubPkiSecretDirectories
    );

    services.vault-auth-setup = mkIf vaultAuthEnabled {
      description = "Bootstrap Vault client environment for LuxNix system services";
      wantedBy = [ "multi-user.target" ];
      after = [
        "local-fs.target"
        "systemd-tmpfiles-setup.service"
        "network-online.target"
      ];
      requires = [ "systemd-tmpfiles-setup.service" ];
      wants = [
        "local-fs.target"
        "network-online.target"
      ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = "root";
        Group = "root";
        UMask = "0077";
        LimitCORE = 0;
        ExecCondition = lib.optionals cfg.client.auth.deferUntilProvisioned [
          vaultAuthProvisioningConditionScript
        ];
        ExecStart =
          if cfg.client.auth.deferUntilProvisioned then
            "${pkgs.coreutils}/bin/true"
          else
            vaultAuthProvisioningConditionScript;
        ExecStop = vaultAuthCleanupScript;
        Environment = lib.optionals cfg.client.allowOffline [
          "VAULT_CLIENT_TIMEOUT=5s"
        ];
        EnvironmentFile = lib.optionals (cfg.client.environmentFile != null) [
          (toString cfg.client.environmentFile)
        ];
      };
      path = [
        pkgs.coreutils
        pkgs.vault
      ];
    };
  };
}
