# Purpose: Define only the lx-annotate-hub-node-provisioning.service unit.
# Command: hubNodeProvisioningScript provisions configured NetworkNode records.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-hub-node-provisioning =
    mkIf cfg.hub.nodeProvisioning.enable
      (mkLxAnnotateAppService {
        description = "Idempotently provision LX-Annotate hub NetworkNode records";
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        wants = [ "lx-annotate-load-base-data.service" ];
        requires = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        before = [
          "lx-annotate.service"
          "lx-annotate-celery-hub-transfer-worker.service"
        ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = hubNodeProvisioningScript;
        };
      });
}
