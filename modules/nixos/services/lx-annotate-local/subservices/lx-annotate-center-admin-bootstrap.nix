# Purpose: Define only the lx-annotate-center-admin-bootstrap.service unit.
# Command: lx-annotate-manage bootstrap_center_admin --username <configured-user>.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-center-admin-bootstrap =
    mkIf (cfg.centerAdminBootstrap.username != null)
      (mkLxAnnotateAppService {
        description = "Bootstrap an authorized LX-Annotate center administrator";
        after = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        wants = [ "lx-annotate-load-base-data.service" ];
        requires = [
          "lx-annotate-load-base-data.service"
          "lx-annotate-master-key-check.service"
        ];
        before = [ "lx-annotate.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = lib.escapeShellArgs [
            "${effectiveRuntimePackage}/bin/lx-annotate-manage"
            "bootstrap_center_admin"
            "--username"
            cfg.centerAdminBootstrap.username
          ];
          TimeoutStartSec = "5min";
        };
      });
}
