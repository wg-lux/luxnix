# Purpose: Define only the lx-annotate-hub-envelope-key-preflight.service unit.
# Command: hubEnvelopeKeyPreflightScript validates envelope recipient keys.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hub-envelope-key-preflight =
    mkIf (cfg.hub.transferApi.enable || cfg.hub.outboundTransfer.enable)
      {
        description = "Validate LX-Annotate Hub envelope recipient identities";
        after = [ "systemd-tmpfiles-setup.service" ] ++ managedSecretsSetupUnits;
        wants = managedSecretsSetupUnits;
        requires = managedSecretsSetupUnits;
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          User = "root";
          Group = "root";
          ExecStart = hubEnvelopeKeyPreflightScript;
          UMask = "0077";
        };
      };
}
