{ lib, lxAnnotateRuntime, ... }:
let
  inherit (lib) mkOption types;
  inherit (lxAnnotateRuntime.paths)
    dataRecoveryStateFile
    legacyRepoDataRootPath
    legacyRepoMediaRootPath
    ;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    dataRecovery = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Expose the legacy data recovery unit for explicitly reviewed maintenance.";
          };
          runBeforeStartup = mkOption {
            type = types.bool;
            default = false;
            description = "Require legacy data recovery before application startup. Enable only for a reviewed legacy migration with a compatible installed recovery command; normal startup uses the existing canonical runtime root.";
          };
          legacyDataDir = mkOption {
            type = types.str;
            default = legacyRepoDataRootPath;
            description = "Legacy repo-local data directory to sync from.";
          };
          legacyMediaDir = mkOption {
            type = types.str;
            default = legacyRepoMediaRootPath;
            description = "Legacy media directory to sync from.";
          };
          stateFile = mkOption {
            type = types.str;
            default = dataRecoveryStateFile;
            description = "Stable state file that records the last effective lx-annotate data directory used for migration drift detection.";
          };
        };
      };
      default = { };
      description = "Recovery settings for migrating legacy lx-annotate media into the runtime storage root.";
    };
  };
}
