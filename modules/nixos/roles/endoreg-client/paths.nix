{ lib, config }:
with lib;
{
  storagePersistingEnable = mkOption {
    type = types.bool;
    default = false;
    description = "Whether to enable persistent storage for endoreg client.";
  };
  storagePersistingIsExternalDrive = mkOption {
    type = types.bool;
    default = false;
    description = "Whether the persistent storage is on an external drive.";
  };
  storagePersistingMountPoint = mkOption {
    type = types.path;
    default = "/mnt/endoreg-client-storage";
    description = "Mount point for persistent storage volume for endoreg client.";
  };

  storageBaseDir = mkOption {
    type = types.path;
    default = "/var/lib/endoreg-client";
    description = "Base directory for endoreg client storage and input directories.";
  };

  dataDir = mkOption {
    type = types.string;
    default = "data";
  };

  desktopDirName = mkOption {
    type = types.str; # Changed from types.path
    default =
      if config.luxnix.generic-settings.language == "english" then
        "Desktop" # removed "home/admin/"
      else
        "Schreibtisch";
  };

  videoInputDir = mkOption {
    type = types.path;
    default = "${config.roles.endoreg-client.paths.storageBaseDir}/input_video";
    description = "Physical directory where videos are dropped.";
  };

  # FIX 3: Anchor this to storageBaseDir (Absolute Path)
  pdfInputDir = mkOption {
    type = types.path;
    default = "${config.roles.endoreg-client.paths.storageBaseDir}/input_pdf";
    description = "Physical directory where PDFs are dropped.";
  };

  desktopPath = mkOption {
    type = types.path;
    default =
      if config.luxnix.generic-settings.language == "english" then
        "home/admin/Desktop"
      else
        "home/admin/Schreibtisch";
    description = "Desktop directory name for the client user (localization support; defaults from luxnix.generic-settings.language).";
  };

  processingRepo = mkOption {
    type = types.string;
    default = "lx-annotate";
  };
}
