{
  config,
  lib,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (lib) mkOption types;
  inherit (lxAnnotateRuntime.defaults)
    emergencyReliefArchiveRootDefault
    emergencyReliefManifestDirDefault
    emergencyReliefStagingDirDefault
    emergencyReliefValidatedExportDirsDefault
    ;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    storageRelief = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Expose the manual emergency storage relief service. The service only archives verified anonymized duplicate payloads and explicitly validated export bundles.";
          };
          dryRun = mkOption {
            type = types.bool;
            default = false;
            description = "Report what emergency storage relief would archive without copying or deleting files.";
          };
          deleteAfterVerify = mkOption {
            type = types.bool;
            default = true;
            description = "Delete local source files only after the external archive copy has been hash-verified.";
          };
          requireExternalMount = mkOption {
            type = types.bool;
            default = true;
            description = "Fail closed unless the external persisting storage mount is active and matches the configured device id or filesystem UUID.";
          };
          externalMountPoint = mkOption {
            type = types.str;
            default = toString config.roles.endoreg-client.paths.storagePersistingMountPoint;
            description = "External mount point used for emergency relief archives.";
          };
          expectedDeviceId = mkOption {
            type = types.nullOr types.str;
            default = config.roles.endoreg-client.paths.storagePersistingDeviceId;
            description = "Expected /dev/disk/by-id basename for the external relief volume. Required when expectedFsUuid is unset.";
          };
          expectedDevicePart = mkOption {
            type = types.str;
            default = config.roles.endoreg-client.paths.storagePersistingDevicePart;
            description = "Partition suffix appended to expectedDeviceId when checking the mounted device.";
          };
          expectedFsUuid = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Optional filesystem UUID accepted for the external relief volume. Use this when the mounted source is a mapper device rather than a plain by-id partition.";
          };
          archiveDir = mkOption {
            type = types.str;
            default = emergencyReliefArchiveRootDefault;
            description = "External archive root for emergency storage relief output.";
          };
          manifestDir = mkOption {
            type = types.str;
            default = emergencyReliefManifestDirDefault;
            description = "External directory where emergency relief JSON manifests are written.";
          };
          stagingDir = mkOption {
            type = types.str;
            default = emergencyReliefStagingDirDefault;
            description = "External staging directory used while emergency relief copies are being verified.";
          };
          includeLegacyProcessedDuplicates = mkOption {
            type = types.bool;
            default = true;
            description = "Archive legacy processed report/video duplicates only when the matching database object is anonymization-export eligible and content hashes match.";
          };
          includeValidatedExportBundles = mkOption {
            type = types.bool;
            default = true;
            description = "Archive export bundles only when they contain a validation marker referencing eligible database resources.";
          };
          validatedExportDirs = mkOption {
            type = types.listOf types.str;
            default = emergencyReliefValidatedExportDirsDefault;
            description = "Directories scanned for validated export bundle marker files.";
          };
          validatedExportMarkerNames = mkOption {
            type = types.listOf types.str;
            default = [ ".lx-annotate-export-validated.json" ];
            description = "Marker filenames that make an export bundle eligible for emergency relief. Marker files must contain JSON with validated=true and eligible resource references.";
          };
          timer = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Run emergency storage relief on a timer. Disabled by default; manual starts are preferred for emergency use.";
                };
                onCalendar = mkOption {
                  type = types.str;
                  default = "hourly";
                  description = "systemd OnCalendar schedule for the emergency relief timer when enabled.";
                };
              };
            };
            default = { };
            description = "Optional timer for emergency storage relief.";
          };
        };
      };
      default = { };
      description = "Emergency storage pressure relief settings for lx-annotate.";
    };
  };
}
