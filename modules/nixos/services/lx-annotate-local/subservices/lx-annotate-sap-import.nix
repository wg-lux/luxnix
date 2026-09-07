# Purpose: Define only the lx-annotate-sap-import.service unit and its matching triggers.
# Command: sapImportServiceScript converts pending SAP zip drops.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-sap-import = mkLxAnnotateAppService {
    description = "Convert SAP IS-H zip drops into preanonymized watcher payload";
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
      PathExistsGlob = [ "${runtimeSapImportDirPath}/*.zip" ];
      Unit = "lx-annotate-sap-import.service";
      MakeDirectory = true;
    };
  };
}
