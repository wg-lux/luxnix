# Migrate to the provisioned active generation without joining the startup chain.
{ ctx }:
with ctx;
let
  enabled = cfg.django.automaticIdentitySaltMigration && cfg.django.identitySaltKeyringFile != null;
in
{
  systemd.services.lx-annotate-identity-salt-migration = mkIf enabled (mkLxAnnotateAppService {
    description = "Migrate verified LX-Annotate identities to the active salt";
    wantedBy = [ ];
    after = [
      "lx-annotate.service"
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    requires = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-manage rotate_identity_salt --apply --allow-partial";
      TimeoutStartSec = "15m";
      Nice = 10;
      IOWeight = 10;
      UMask = "0077";
    };
  });

  systemd.timers.lx-annotate-identity-salt-migration = mkIf enabled {
    description = "Retry LX-Annotate identity salt migration in the background";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "10m";
      OnUnitInactiveSec = "1h";
      RandomizedDelaySec = "1m";
      Unit = "lx-annotate-identity-salt-migration.service";
    };
  };
}
