# Purpose: Define only the lx-annotate-export-frames.service unit.
# Command: lx-annotate-export-frames.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-export-frames = mkLxAnnotateAppService {
    description = "Export annotated frames for LX-Annotate";
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
    environment = {
      LX_ANNOTATE_EXPORT_FRAMES_OUTPUT_DIR = "${runtimeStorageRootPath}/export/frames";
    };
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${effectiveRuntimePackage}/bin/lx-annotate-export-frames";
    };
  };
}
