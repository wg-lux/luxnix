# Purpose: Define only the lx-annotate-runtime-env.service unit.
# Command: runtimeEnvScript prepares the canonical .env.systemd files.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-runtime-env = {
    description = "Prepare LuxNix runtime environment for lx-annotate";
    before = [
      "lx-annotate.service"
      "lx-annotate-master-key-check.service"
    ];
    after = [
      "systemd-tmpfiles-setup.service"
    ]
    ++ managedSecretsSetupUnits
    ++ localPostgresSetupUnits;
    wants = managedSecretsSetupUnits ++ localPostgresSetupUnits;
    requires = managedSecretsSetupUnits;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = "root";
      ExecStart = runtimeEnvScript;
      LogNamespace = lxAnnotateJournalNamespace;
    };
  };
}
