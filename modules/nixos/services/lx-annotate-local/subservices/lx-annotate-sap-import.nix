# Purpose: Define only the lx-annotate-sap-import.service unit and its matching triggers.
# Command: sapImportServiceScript converts pending SAP zip drops.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-sap-import = mkLxAnnotateAppService {
    description = "Convert SAP IS-H zip drops into preanonymized watcher payload";
    background = true;
    wantedBy = [ ];
    after = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    wants = [ "lx-annotate-load-base-data.service" ];
    requires = [
      "lx-annotate-load-base-data.service"
      "lx-annotate-master-key-check.service"
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = sapImportServiceScript;
    };
  };

  systemd.paths.lx-annotate-sap-import = {
    description = "Trigger SAP IS-H zip conversion when SAP drops exist";
    wantedBy = [ "multi-user.target" ];
    pathConfig = {
      PathChanged = [ runtimeSapImportDirPath ];
      Unit = "lx-annotate-sap-import.service";
      MakeDirectory = true;
    };
  };
  systemd.timers.lx-annotate-sap-import = {
    description = "Retry pending SAP IS-H zip imports";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "2m";
      OnUnitInactiveSec = "5m";
      RandomizedDelaySec = "30s";
      Unit = "lx-annotate-sap-import.service";
    };
  };
}
