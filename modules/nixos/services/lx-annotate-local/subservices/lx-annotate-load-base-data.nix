# Purpose: Define only the lx-annotate-load-base-data.service unit.
# Command: lx-annotate-load-base-data.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-load-base-data = mkLxAnnotateAppService {
    description = "Load LX-Annotate base data";
    after = [ "lx-annotate-migrate.service" ];
    wants = [ "lx-annotate-migrate.service" ];
    requires = [ "lx-annotate-migrate.service" ];
    before = [
      "lx-annotate-master-key-check.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = loadBaseDataServiceScript;
      TimeoutStartSec = "10min";
    };
  };
}
