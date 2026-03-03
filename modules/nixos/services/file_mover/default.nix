{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.fileMover;
  endoregPaths = config.roles.endoreg-client.paths;

  clientUserName =
    if config ? user && config.user ? client && config.user.client ? name then
      config.user.client.name
    else
      "client-user";

  adminUserName =
    if config ? user && config.user ? admin && config.user.admin ? name then
      config.user.admin.name
    else
      "admin-user";

  endoregServiceUserName = config.user.endoreg-service-user.name;
  endoregServiceGroup = "endoreg-service";

  endoreg-service-user-home = config.users.users.${endoregServiceUserName}.home;
  repoDirName = "lx-annotate";

  # Source paths
  sourceVideoDir = endoregPaths.videoInputDir;
  sourcePdfDir = endoregPaths.pdfInputDir;
  failedInputBaseDir = "${endoregPaths.storageBaseDir}/failed_input";
  failedVideoDir = "${failedInputBaseDir}/video";
  failedPdfDir = "${failedInputBaseDir}/pdf";

  # Destination paths (Deep inside the repo)
  destVideoDir = "${endoreg-service-user-home}/${repoDirName}/data/import/video_import";
  destReportDir = "${endoreg-service-user-home}/${repoDirName}/data/import/report_import";

  # Resolve the correct desktop name (Schreibtisch vs Desktop)
  resolvedDesktopName = config.roles.endoreg-client.paths.desktopDirName;

in
{
  options.services.luxnix.fileMover = {
    enable = mkBoolOpt false "Enable the move-my-files path-triggered service.";
  };

  config = mkIf cfg.enable {

    # 1. Ensure directories exist (Source & Dest)
    systemd.tmpfiles.rules = [
      "d \"${sourceVideoDir}\" 0770 root ${endoregServiceGroup} -"
      "d \"${sourcePdfDir}\" 0770 root ${endoregServiceGroup} -"
      "d \"${failedVideoDir}\" 0770 root ${endoregServiceGroup} -"
      "d \"${failedPdfDir}\" 0770 root ${endoregServiceGroup} -"
      # Create destination parents if they don't exist yet (Repo might be cloning)
      "d \"${endoreg-service-user-home}/${repoDirName}/data/import\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destVideoDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destReportDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
    ];

    # 2. Home Manager: Use the resolved variable for Desktop/Schreibtisch
    home-manager.users = {
      ${clientUserName} =
        { config, ... }:
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
      ${adminUserName} =
        { config, ... }:
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
        # ExecStartPre runs as root and normalizes source permissions before rsync.
        PermissionsStartOnly = true;
        ExecStartPre = "${pkgs.writeShellScript "move-my-files-prepare-inputs" ''
          set -euo pipefail

          for dir in "${sourceVideoDir}" "${sourcePdfDir}" "${failedVideoDir}" "${failedPdfDir}"; do
            ${pkgs.coreutils}/bin/install -d -m 2770 -o root -g ${endoregServiceGroup} "$dir"
          done

          normalize_tree_permissions() {
            local source_dir="$1"
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -exec ${pkgs.coreutils}/bin/chgrp ${endoregServiceGroup} {} + || true
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type d -exec ${pkgs.coreutils}/bin/chmod g+rws,o-rwx {} + || true
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f -exec ${pkgs.coreutils}/bin/chmod g+rw,o-rwx {} + || true
          }

          normalize_tree_permissions "${sourceVideoDir}"
          normalize_tree_permissions "${sourcePdfDir}"
        ''}";
      };

      script = ''
        set -euo pipefail

        # Safety check: Ensure destination exists (repository might have just finished cloning)
        mkdir -p "${destVideoDir}" "${destReportDir}" "${failedVideoDir}" "${failedPdfDir}"

        # Settle time for large file copies
        sleep 2

        overall_status=0

        quarantine_unreadable_files() {
          local source_dir="$1"
          local quarantine_dir="$2"
          local label="$3"

          while IFS= read -r -d "" unreadable_file; do
            base_name="$(${pkgs.coreutils}/bin/basename "$unreadable_file")"
            timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%d-%H%M%S)"
            quarantine_target="''${quarantine_dir}/''${timestamp}-''${base_name}"
            echo "Warning: ''${label} file unreadable by ${endoregServiceUserName}. Quarantining: $unreadable_file"

            if ! ${pkgs.coreutils}/bin/mv -f "$unreadable_file" "$quarantine_target"; then
              echo "Warning: Failed to quarantine unreadable file: $unreadable_file"
              overall_status=1
            fi
          done < <(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f ! -readable -print0)
        }

        process_input_dir() {
          local source_dir="$1"
          local dest_dir="$2"
          local quarantine_dir="$3"
          local label="$4"

          if [ -z "$(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -print -quit)" ]; then
            return 0
          fi

          echo "Processing ''${label} Input..."
          quarantine_unreadable_files "$source_dir" "$quarantine_dir" "$label"

          # If everything was quarantined, there's nothing left to sync.
          if [ -z "$(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -print -quit)" ]; then
            return 0
          fi

          if ! ${pkgs.rsync}/bin/rsync -av --omit-dir-times --remove-source-files --chmod=F660,D770 --chown=${endoregServiceUserName}:${endoregServiceGroup} "''${source_dir}/" "''${dest_dir}/"; then
            echo "Warning: rsync ''${label} failed. Files remain and will trigger restart."
            overall_status=1
          fi
        }

        # Rsync with retry logic is not needed here because Systemd will re-trigger
        # if files are left behind.
        process_input_dir "${sourceVideoDir}" "${destVideoDir}" "${failedVideoDir}" "Video"
        process_input_dir "${sourcePdfDir}" "${destReportDir}" "${failedPdfDir}" "PDF"

        # Cleanup empty dirs in Source (ignore errors)
        ${pkgs.findutils}/bin/find "${sourceVideoDir}" -mindepth 1 -type d -empty -delete || true
        ${pkgs.findutils}/bin/find "${sourcePdfDir}" -mindepth 1 -type d -empty -delete || true

        exit "$overall_status"
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
