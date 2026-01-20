{ config, lib, pkgs, ... }:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.fileMover;
  endoregPaths = config.roles.endoreg-client.paths;

  clientUserName =
    if config ? user && config.user ? client && config.user.client ? name
    then config.user.client.name
    else "client-user";

  endoregServiceUserName = config.user.endoreg-service-user.name;
  # Use the service group for permissions so both admin and service user can access
  endoregServiceGroup = "endoreg-service"; 
  
  endoregServiceUserHome = config.users.users.${endoregServiceUserName}.home;
  repoDirName = "lx-annotate";
  repoDir = "${endoregServiceUserHome}/${repoDirName}";
  makeAbsolute = path: if lib.hasPrefix "/" path then path else "${repoDir}/${path}";
  
  # Source paths (clean vars for tmpfiles and path unit)
  sourceVideoDir = endoregPaths.videoInputDir;
  sourcePdfDir = endoregPaths.pdfInputDir;
  
  # Destination paths (clean vars for tmpfiles and service)
  destVideoDir = "${repoDir}/import/video_import";
  destReportDir = "${repoDir}/import/report_import";

in {
  options.services.luxnix.fileMover = {
    enable = mkBoolOpt true "Enable the move-my-files path-triggered service.";
  };

  config = mkIf cfg.enable {

    # 1. ROBUSTNESS: Ensure directories exist via tmpfiles.
    # We define both source and destination here to keep the path unit reliable.
    systemd.tmpfiles.rules = [
      "d \"${sourceVideoDir}\" 0777 root ${endoregServiceGroup} -"
      "d \"${sourcePdfDir}\" 0777 root ${endoregServiceGroup} -"
      "d \"${destVideoDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
      "d \"${destReportDir}\" 0770 ${endoregServiceUserName} ${endoregServiceGroup} -"
    ];

    # Home Manager links are only created if the Client Role is DISABLED.
    # If the Client Role is enabled, IT handles the desktop links.
    home-manager.users = optionalAttrs (!config.roles.endoreg-client.enable) {
      ${clientUserName} = { config, ... }:
        let
          outOfStore = config.lib.file.mkOutOfStoreSymlink;
        in
        {
          xdg.userDirs = {
            enable = true;
            createDirectories = true;
          };

          home.file."${config.xdg.userDirs.desktop}/Video_Input" = {
            source = outOfStore sourceVideoDir;
          };

          home.file."${config.xdg.userDirs.desktop}/PDF_Input" = {
            source = outOfStore sourcePdfDir;
          };
        };
    };

    # 2. The Service (The worker)
    systemd.services.move-my-files = {
      description = "Move files from Source to Destination";
      serviceConfig = {
        Type = "oneshot";
        # We run as the Admin user, but we must ensure Admin is in the 'endoreg-service' group
        # so they can read the Source (0770 root:endoreg-service) and write to Dest.
        User = config.user.admin.name;
        Group = endoregServiceGroup; 
      };

      script = ''
        set -euo pipefail

        # Eager creation in case a user manually deleted a folder while the PC was on.
        ${pkgs.coreutils}/bin/mkdir -p "${sourceVideoDir}" "${destVideoDir}"
        ${pkgs.coreutils}/bin/mkdir -p "${sourcePdfDir}" "${destReportDir}"

        # We add a tiny sleep to ensure the file system settles if a file was JUST touched
        sleep 2

        # Run Rsync
        # We use quoted paths to handle spaces in directory names
        ${pkgs.rsync}/bin/rsync -av --omit-dir-times --remove-source-files --chmod=F660,D770 "${sourceVideoDir}/" "${destVideoDir}/" || echo "Warning: rsync video failed with exit code $?"
        ${pkgs.rsync}/bin/rsync -av --omit-dir-times --remove-source-files --chmod=F660,D770 "${sourcePdfDir}/" "${destReportDir}/" || echo "Warning: rsync report failed with exit code $?"

        # Cleanup empty dirs in Source
        ${pkgs.findutils}/bin/find "${sourceVideoDir}" -mindepth 1 -type d -empty -delete || true
        ${pkgs.findutils}/bin/find "${sourcePdfDir}" -mindepth 1 -type d -empty -delete || true
      '';
    };

    # 3. The Path Unit (The trigger)
    systemd.paths.move-my-files = {
      description = "Trigger move-my-files when inputs change";
      wantedBy = [ "multi-user.target" ];
      after = [ "systemd-tmpfiles-setup.service" ];
      pathConfig = {
        PathChanged = [
          sourceVideoDir
          sourcePdfDir
        ];
        Unit = "move-my-files.service";
      };
    };
  };
}
