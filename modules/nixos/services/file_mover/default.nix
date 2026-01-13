{ config, lib, pkgs, ... }:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.fileMover;
  
  # Define paths in variables so we don't typo them between the 3 sections
  sourceVideo = "/home/admin/Desktop/video_import/";
  sourceReport = "/home/admin/Desktop/report_import/";
  destVideo = "/home/admin/dev/lx-annotate/data/import/video_import/";
  destReport = "/home/admin/dev/lx-annotate/data/import/report_import/";
in {
  options.services.luxnix.fileMover = {
    enable = mkBoolOpt false "Enable the move-my-files path-triggered service.";
  };

  config = mkIf cfg.enable {

    # 1. FIXED: Ensure directories exist BEFORE the Path Watcher starts
    # Syntax: type path mode user group age argument
    systemd.tmpfiles.rules = [
      "d ${sourceVideo} 0755 ${config.user.admin.name} users -"
      "d ${sourceReport} 0755 ${config.user.admin.name} users -"
      "d ${destVideo} 0755 ${config.user.admin.name} users -"
      "d ${destReport} 0755 ${config.user.admin.name} users -"
    ];

    # 2. The Service (The worker)
    systemd.services.move-my-files = {
      description = "Move files from Source to Destination";
      serviceConfig = {
        Type = "oneshot";
        User = config.user.admin.name;
      };

      script = ''
        # Redundant mkdir is harmless, but tmpfiles handles it now.
        # We assume variables are hardcoded or passed here, but for safety 
        # let's redeclare them inside the script to match your previous style 
        # or use the let block variables interpolated:
        
        SOURCEVIDEO="${sourceVideo}"
        SOURCEREPORT="${sourceReport}"
        DESTVIDEO="${destVideo}"
        DESTREPORT="${destReport}"

        # We add a tiny sleep to ensure the file system settles if a file was JUST touched
        sleep 2

        # Run Rsync
        ${pkgs.rsync}/bin/rsync -av --remove-source-files --chmod=F660,D770 "$SOURCEVIDEO" "$DESTVIDEO" || true
        ${pkgs.rsync}/bin/rsync -av --remove-source-files --chmod=F660,D770 "$SOURCEREPORT" "$DESTREPORT" || true

        # Cleanup empty dirs
        ${pkgs.findutils}/bin/find "$SOURCEVIDEO" -mindepth 1 -type d -empty -delete
        ${pkgs.findutils}/bin/find "$SOURCEREPORT" -mindepth 1 -type d -empty -delete
      '';
    };

    # 3. The Path Watcher (The trigger)
    systemd.paths.move-my-files = {
      wantedBy = [ "paths.target" ];
      pathConfig = {
        # PathChanged triggers when a file is closed after writing
        PathChanged = [
          sourceVideo
          sourceReport
        ];
        Unit = "move-my-files.service";
      };
    };
  };
}