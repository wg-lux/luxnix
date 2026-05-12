{ config
, lib
, pkgs
, ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.fileMover;
  endoregPaths = config.roles.endoreg-client.paths;
  lxAnnotateCfg = config.services.luxnix.lxAnnotateLocal;

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
  runtimeDataDir = lxAnnotateCfg.runtime.encryptedDataDir;
  intakeDirs = lxAnnotateCfg.runtime.intakeDirs;
  resolveRuntimeDataPath = path:
    let
      pathString = toString path;
    in
    if lib.hasPrefix "/" pathString then
      pathString
    else if pathString == "data" then
      runtimeDataDir
    else if lib.hasPrefix "data/" pathString then
      "${runtimeDataDir}/${lib.removePrefix "data/" pathString}"
    else
      "${runtimeDataDir}/${pathString}";
  # Intake destinations must stay aligned with the lx-annotate runtime contract:
  # services.luxnix.lxAnnotateLocal.runtime.intakeDirs, which mirrors the
  # watcher path names exported by lx-annotate secretspec.toml.
  runtimeIoDir = resolveRuntimeDataPath intakeDirs.importRoot;
  runtimePreanonymizedDir = resolveRuntimeDataPath intakeDirs.preanonymized;
  runtimeSapImportDir = resolveRuntimeDataPath intakeDirs.sap;
  runtimeMoverStagingDir = resolveRuntimeDataPath intakeDirs.moverStaging;
  serviceUserIoAccessLink = "${endoreg-service-user-home}/lx-annotate-io";
  desktopPreanonymizedLinkTarget = "${serviceUserIoAccessLink}/preanonymized_import";
  desktopSapImportLinkTarget = "${serviceUserIoAccessLink}/sap_import";

  # Destination watcher intake paths for both repo and wheel deployments.
  destVideoDir = resolveRuntimeDataPath intakeDirs.video;
  destReportDir = resolveRuntimeDataPath intakeDirs.report;

  # Resolve the correct desktop name (Schreibtisch vs Desktop)
  resolvedDesktopName = config.roles.endoreg-client.paths.desktopDirName;
  desktopLinkNames = [
    "Video_Input"
    "PDF_Input"
    "preanonymized_import"
    "sap_import"
  ];
  prepareDesktopLinksActivation = ''
    desktop_dir="$HOME/${resolvedDesktopName}"

    for link_name in ${lib.concatMapStringsSep " " lib.escapeShellArg desktopLinkNames}; do
      target_path="$desktop_dir/$link_name"

      if [ -e "$target_path" ] && [ ! -L "$target_path" ]; then
        timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%d-%H%M%S)"
        backup_path="$target_path.luxnix-backup-$timestamp"
        counter=1

        while [ -e "$backup_path" ]; do
          backup_path="$target_path.luxnix-backup-$timestamp-$counter"
          counter=$((counter + 1))
        done

        echo "Preserving unmanaged file mover desktop path: $target_path -> $backup_path"
        ${pkgs.coreutils}/bin/mv -- "$target_path" "$backup_path"
      fi
    done
  '';

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
      # Create runtime intake directories.
      "d \"${runtimeIoDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destVideoDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destReportDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${runtimePreanonymizedDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${runtimeSapImportDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
    ];

    # 2. Home Manager: Use the resolved variable for Desktop/Schreibtisch
    home-manager.users = {
      ${clientUserName} =
        { config, lib, ... }:
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

          home.file."${resolvedDesktopName}/preanonymized_import" = {
            source = outOfStore desktopPreanonymizedLinkTarget;
          };

          home.file."${resolvedDesktopName}/sap_import" = {
            source = outOfStore desktopSapImportLinkTarget;
          };

          home.activation.prepareFileMoverDesktopLinks =
            lib.hm.dag.entryBefore [ "checkLinkTargets" ] prepareDesktopLinksActivation;
        };

      ${adminUserName} =
        { config, lib, ... }:
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

          home.file."${resolvedDesktopName}/preanonymized_import" = {
            source = outOfStore desktopPreanonymizedLinkTarget;
          };

          home.file."${resolvedDesktopName}/sap_import" = {
            source = outOfStore desktopSapImportLinkTarget;
          };

          home.activation.prepareFileMoverDesktopLinks =
            lib.hm.dag.entryBefore [ "checkLinkTargets" ] prepareDesktopLinksActivation;
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

          staging_dir="${runtimeMoverStagingDir}/''${label}"
          manifest_file="${runtimeMoverStagingDir}/''${label}.files"
          publish_status=0
          ${pkgs.coreutils}/bin/rm -rf "$staging_dir"
          ${pkgs.coreutils}/bin/rm -f "$manifest_file"
          ${pkgs.coreutils}/bin/install -d -m 0770 -o ${endoregServiceUserName} -g ${endoregServiceGroup} "$staging_dir" "$dest_dir"

          if ! ${pkgs.rsync}/bin/rsync -av --omit-dir-times --chmod=F660,D770 --chown=${endoregServiceUserName}:${endoregServiceGroup} "''${source_dir}/" "''${staging_dir}/"; then
            echo "Warning: rsync ''${label} into staging failed. Files remain and will trigger restart."
            overall_status=1
            return 0
          fi

          ${pkgs.findutils}/bin/find "$staging_dir" -mindepth 1 -type d -exec ${pkgs.coreutils}/bin/chmod 0770 {} +
          ${pkgs.findutils}/bin/find "$staging_dir" -mindepth 1 -type f -exec ${pkgs.coreutils}/bin/chmod 0660 {} +
          ${pkgs.findutils}/bin/find "$staging_dir" -type f -printf '%P\0' > "$manifest_file"

          while IFS= read -r -d "" staged_entry; do
            entry_name="$(${pkgs.coreutils}/bin/basename "$staged_entry")"
            if ! ${pkgs.coreutils}/bin/mv -f "$staged_entry" "''${dest_dir}/''${entry_name}"; then
              echo "Warning: failed to publish staged ''${label} entry: $staged_entry"
              publish_status=1
              overall_status=1
            fi
          done < <(${pkgs.findutils}/bin/find "$staging_dir" -mindepth 1 -maxdepth 1 -print0)

          if [ "$publish_status" -eq 0 ]; then
            while IFS= read -r -d "" source_relative_path; do
              ${pkgs.coreutils}/bin/rm -f "''${source_dir}/''${source_relative_path}" || true
            done < "$manifest_file"
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type d -empty -delete || true
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
