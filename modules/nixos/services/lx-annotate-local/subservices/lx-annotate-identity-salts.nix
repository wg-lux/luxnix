# Local creation/recovery is required before settings load; bulk migration is separate.
{ ctx }:
with ctx;
let
  python = pkgs.python3.withPackages (ps: [ ps.pyyaml ]);
  provision = pkgs.writeShellScript "lx-annotate-provision-identity-salts" ''
    exec ${python}/bin/python ${../../../../../scripts/provision-identity-salts.py} \
      --secret-dir /etc/secrets/vault \
      --recovery-dir /var/lib/lx-annotate-identity-salts \
      --replica-dir ${lib.escapeShellArg "${envDataDir}/.identity-salt-recovery"} \
      --user ${lib.escapeShellArg endoreg-service-user-name} \
      --group ${lib.escapeShellArg endoreg-service-group-name}
  '';
in
mkIf cfg.django.enrollLegacyDefaultSalt {
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
