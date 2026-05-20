args@{ lib, ... }:
with lib;
with args;
let
  runtime = lxAnnotateRuntime;
  inherit (runtime.paths) envDataDir;
  inherit (runtime.defaults)
    processedReportDirName
    processedVideoDirName
    ;
in
{
  emergencyStorageReliefConfig = pkgs.writeText "lx-annotate-emergency-storage-relief-config.json" (
    builtins.toJSON {
      archive_root = cfg.storageRelief.archiveDir;
      manifest_dir = cfg.storageRelief.manifestDir;
      staging_dir = cfg.storageRelief.stagingDir;
      external_mount_point = cfg.storageRelief.externalMountPoint;
      runtime_root = envDataDir;
      dry_run = cfg.storageRelief.dryRun;
      delete_after_verify = cfg.storageRelief.deleteAfterVerify;
      include_legacy_processed_duplicates = cfg.storageRelief.includeLegacyProcessedDuplicates;
      include_validated_export_bundles = cfg.storageRelief.includeValidatedExportBundles;
      validated_export_dirs = cfg.storageRelief.validatedExportDirs;
      validated_export_marker_names = cfg.storageRelief.validatedExportMarkerNames;
      legacy_duplicate_sources = [
        {
          kind = "report";
          source_root = cfg.dataCleanup.legacyProcessedReportDir;
          label = "legacy-data/${processedReportDirName}";
        }
        {
          kind = "video";
          source_root = cfg.dataCleanup.legacyProcessedVideoDir;
          label = "legacy-data/${processedVideoDirName}";
        }
        {
          kind = "report";
          source_root = cfg.dataCleanup.legacyMediaProcessedReportDir;
          label = "legacy-media/${processedReportDirName}";
        }
        {
          kind = "video";
          source_root = cfg.dataCleanup.legacyMediaProcessedVideoDir;
          label = "legacy-media/${processedVideoDirName}";
        }
      ];
    }
  );

  emergencyStorageReliefHelper = pkgs.writeText "lx-annotate-emergency-storage-relief.py" (
    builtins.readFile ./storage-relief.py
  );
}
