{ config, lib, pkgs, ... }:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.fileMover;
  endoregPaths = config.roles.endoreg-client.paths;

  clientUserName =
    if config ? user && config.user ? client && config.user.client ? name
    then config.user.client.name
    else "client-user";

  adminUserName =
    if config ? user && config.user ? admin && config.user.admin ? name
    then config.user.admin.name
    else "admin-user";

  endoregServiceUserName = config.user.endoreg-service-user.name;
  endoregServiceGroup = "endoreg-service"; 
  
  endoreg-service-user-home = config.users.users.${endoregServiceUserName}.home;
  repoDirName = "lx-annotate";
  
  # Source paths
  sourceVideoDir = endoregPaths.videoInputDir;
  sourcePdfDir = endoregPaths.pdfInputDir;
  
  # Destination paths (Deep inside the repo)
  destVideoDir = "${endoreg-service-user-home}/${repoDirName}/data/import/video_import";
  destReportDir = "${endoreg-service-user-home}/${repoDirName}/data/import/report_import";

  # Resolve the correct desktop name (Schreibtisch vs Desktop)
  resolvedDesktopName = config.roles.endoreg-client.paths.desktopDirName;

in {
  options.services.luxnix.fileMover = {
    enable = mkBoolOpt true "Enable the move-my-files path-triggered service.";
  };

  config = mkIf cfg.enable {

    # 1. Ensure directories exist (Source & Dest)
    systemd.tmpfiles.rules = [
      "d \"${sourceVideoDir}\" 0777 root ${endoregServiceGroup} -"
      "d \"${sourcePdfDir}\" 0777 root ${endoregServiceGroup} -"
      # Create destination parents if they don't exist yet (Repo might be cloning)
      "d \"${endoreg-service-user-home}/${repoDirName}/data/import\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destVideoDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destReportDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
    ];

    # 2. Home Manager: Use the resolved variable for Desktop/Schreibtisch
    home-manager.users = {
      ${clientUserName} = { config, ... }:
        let
          outOfStore = config.lib.file.mkOutOfStoreSymlink;
        in
        {
          xdg.userDirs = {
            enable = true;
            createDirectories = true;
            extraConfig = {
              XDG_DESKTOP_DIR = "${config.home.homeDirectory}/${resolvedDesktopName}";
            };
          };

          home.file."${resolvedDesktopName}/Video_Input" = {
            source = outOfStore sourceVideoDir;
          };

          home.file."${resolvedDesktopName}/PDF_Input" = {
            source = outOfStore sourcePdfDir;
          };
        };
    };
    home-manager.users = {
      ${adminUserName} = { config, ... }:
        let
          outOfStore = config.lib.file.mkOutOfStoreSymlink;
        in
        {
          xdg.userDirs = {
            enable = true;
            createDirectories = true;
            extraConfig = {
              XDG_DESKTOP_DIR = "${config.home.homeDirectory}/${resolvedDesktopName}";
            };
          };

          home.file."${resolvedDesktopName}/Video_Input" = {
            source = outOfStore sourceVideoDir;
          };

          home.file."${resolvedDesktopName}/PDF_Input" = {
            source = outOfStore sourcePdfDir;
          };
        };
    };

    # 3. The Worker Service
    systemd.services.move-my-files = {
      description = "Move files from Source to Destination";
      serviceConfig = {
        Type = "oneshot";
        User = endoregServiceUserName;
        Group = endoregServiceGroup; 
      };

      script = ''
        set -euo pipefail

        

        # Safety check: Ensure destination exists (repository might have just finished cloning)
        mkdir -p "${destVideoDir}" "${destReportDir}"
        

        # Settle time for large file copies
        sleep 2

        # Rsync with retry logic is not needed here because Systemd will re-trigger
        # if files are left behind.
        
        # 1. Video Input
        if [ -n "$(${pkgs.findutils}/bin/find "${sourceVideoDir}" -mindepth 1 -print -quit)" ]; then
            echo "Processing Video Input..."
            ${pkgs.rsync}/bin/rsync -av --omit-dir-times --remove-source-files --chmod=F660,D770 "${sourceVideoDir}/" "${destVideoDir}/" || {
                echo "Warning: rsync video failed. Files remain and will trigger restart."
                exit 1 
            }
        fi

        # 2. PDF Input
        if [ -n "$(${pkgs.findutils}/bin/find "${sourcePdfDir}" -mindepth 1 -print -quit)" ]; then
            echo "Processing PDF Input..."
            ${pkgs.rsync}/bin/rsync -av --omit-dir-times --remove-source-files --chmod=F660,D770 "${sourcePdfDir}/" "${destReportDir}/" || {
                 echo "Warning: rsync report failed. Files remain and will trigger restart."
                 exit 1
            }
        fi

        # Cleanup empty dirs in Source (ignore errors)
        ${pkgs.findutils}/bin/find "${sourceVideoDir}" -mindepth 1 -type d -empty -delete || true
        ${pkgs.findutils}/bin/find "${sourcePdfDir}" -mindepth 1 -type d -empty -delete || true
      '';
    };

    # 4. The Trigger: DirectoryNotEmpty
    # This ensures that if rsync failed (files remain), or new files were added
    # while rsync was running, the service triggers again immediately.
    systemd.paths.move-my-files = {
      description = "Trigger move-my-files when content exists";
      wantedBy = [ "multi-user.target" ];
      pathConfig = {
        DirectoryNotEmpty = [
          sourceVideoDir
          sourcePdfDir
        ];
        Unit = "move-my-files.service";
        MakeDirectory = true;
      };
    };
  };
}
