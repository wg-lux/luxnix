# Local creation/recovery is required before settings load; bulk migration is separate.
{ ctx }:
with ctx;
let
  python = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
  centerKey = config.roles.endoreg-client.defaultCenterKey;
  centerSaltFile = "/etc/secrets/vault/lx_annotate_center_${centerKey}_identity";
  centerSaltPath = "${config.luxnix.vault.client.hubPki.kvMountPath}/centers/${centerKey}/identity";
  provisioner = pkgs.runCommand "identity-salt-provisioner" { } ''
    mkdir -p "$out"
    cp ${../../../../../scripts/provision-identity-salts.py} "$out/provision-identity-salts.py"
    cp ${../../../../../lx_administration/secret_storage.py} "$out/verify-secret-storage.py"
  '';
  provision = pkgs.writeShellScript "lx-annotate-provision-identity-salts" ''
    export PATH=${lib.makeBinPath [ pkgs.util-linux ]}:"$PATH"
    exec ${python}/bin/python ${provisioner}/provision-identity-salts.py \
      --secret-dir /etc/secrets/vault \
      --recovery-dir /var/lib/lx-annotate-identity-salts \
      --replica-dir ${lib.escapeShellArg "${envDataDir}/.identity-salt-recovery"} \
      --user ${lib.escapeShellArg endoreg-service-user-name} \
      --group ${lib.escapeShellArg endoreg-service-group-name} \
      ${lib.optionalString cfg.django.centerIdentitySalt "--source-salt ${lib.escapeShellArg centerSaltFile} --center-id ${lib.escapeShellArg centerKey}"}
  '';
in
mkIf (cfg.django.enrollLegacyDefaultSalt && !cfg.django.identitySaltViaSecretSpec) {
  assertions = lib.optional cfg.django.centerIdentitySalt {
    assertion = builtins.match "[A-Za-z0-9_-]+" centerKey != null
      && config.luxnix.vault.client.hubPki.enable
      && !config.luxnix.vault.client.auth.deferUntilProvisioned;
    message = "Center identity salt requires a stable center key and enrolled Vault machine authentication.";
  };
  roles.managed-secrets.customSecrets.lx_annotate_center_identity_source =
    mkIf cfg.django.centerIdentitySalt {
      path = centerSaltFile;
      owner = "root";
      group = "root";
      permissions = "600";
      description = "Vault-managed center identity salt";
      customScript = true;
      refreshOnBoot = true;
      generator = ''
        ${pkgs.vault}/bin/vault kv get -field=salt ${lib.escapeShellArg centerSaltPath} > "$TARGET_FILE"
        test -s "$TARGET_FILE"
      '';
    };
  # Root-only recovery material is retained independently of prunable app snapshots.
  services.luxnix.lxAnnotateLocal.hub.backup.exclude = mkAfter [ ".identity-salt-recovery" ];
  systemd = {
    services.lx-annotate-identity-salts = {
      description = "Preserve, recover and provision LX-Annotate identity salts";
      after = [ "systemd-tmpfiles-setup.service" ] ++ managedSecretsSetupUnits ++ encryptionServiceUnits;
      requires = managedSecretsSetupUnits ++ encryptionServiceUnits;
      unitConfig = encryptedDataMountUnitConfig;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = provision;
        StateDirectory = "lx-annotate-identity-salts";
        StateDirectoryMode = "0700";
        UMask = "0077";
        LimitCORE = 0;
        User = "root";
        LogNamespace = lxAnnotateJournalNamespace;
        TimeoutStartSec = "1m";
        ProtectSystem = "strict";
        ReadWritePaths = [
          "/etc/secrets/vault"
          "/var/lib/lx-annotate-identity-salts"
          envDataDir
        ];
        PrivateTmp = true;
        NoNewPrivileges = true;
      };
    };
    services.lx-annotate-runtime-env = {
      after = [ "lx-annotate-identity-salts.service" ];
      requires = [ "lx-annotate-identity-salts.service" ];
    };
    timers.lx-annotate-identity-salts = {
      description = "Repair missing LX-Annotate salt copies without rotating identities";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "15m";
        OnUnitInactiveSec = "15m";
      };
    };
  };
}
