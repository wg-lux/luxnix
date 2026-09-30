{
  config,
  lib,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (lib) mkOption types;
  inherit (lxAnnotateRuntime.defaults) externalCleanupArchiveRootDefault;
  inherit (lxAnnotateRuntime.paths)
    legacyRepoDataRootPath
    legacyRepoMediaRootPath
    legacyDataProcessedReportDir
    legacyDataProcessedVideoDir
    legacyMediaProcessedReportDir
    legacyMediaProcessedVideoDir
    runtimeProcessedReportDir
    runtimeProcessedVideoDir
    ;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    dataCleanup = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = config.roles.endoreg-client.paths.storagePersistingEnable;
            description = "Regularly move duplicate anonymized lx-annotate payload into external archive storage.";
          };
          legacyDataDir = mkOption {
            type = types.str;
            default = legacyRepoDataRootPath;
            description = "Legacy repo-local data directory to clean up.";
          };
          legacyMediaDir = mkOption {
            type = types.str;
            default = legacyRepoMediaRootPath;
            description = "Legacy media directory to clean up.";
          };
          legacyProcessedReportDir = mkOption {
            type = types.str;
            default = legacyDataProcessedReportDir;
            description = "Legacy processed report directory derived from the lx-annotate service paths.";
          };
          legacyProcessedVideoDir = mkOption {
            type = types.str;
            default = legacyDataProcessedVideoDir;
            description = "Legacy processed video directory derived from the lx-annotate service paths.";
          };
          legacyMediaProcessedReportDir = mkOption {
            type = types.str;
            default = legacyMediaProcessedReportDir;
            description = "Legacy processed report directory under the service media root.";
          };
          legacyMediaProcessedVideoDir = mkOption {
            type = types.str;
            default = legacyMediaProcessedVideoDir;
            description = "Legacy processed video directory under the service media root.";
          };
          archiveDir = mkOption {
            type = types.str;
            default = externalCleanupArchiveRootDefault;
            description = "External archive directory where duplicate files are moved.";
          };
          runtimeProcessedReportDir = mkOption {
            type = types.str;
            default = runtimeProcessedReportDir;
            description = "Runtime processed report directory derived from the lx-annotate service.";
          };
          runtimeProcessedVideoDir = mkOption {
            type = types.str;
            default = runtimeProcessedVideoDir;
            description = "Runtime processed video directory derived from the lx-annotate service.";
          };
          onCalendar = mkOption {
            type = types.str;
            default = "daily";
            description = "systemd timer schedule for duplicate cleanup.";
          };
        };
      };
      default = { };
      description = "Duplicate cleanup settings for anonymized lx-annotate legacy storage.";
    };
  };
}
