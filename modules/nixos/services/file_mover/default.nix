{ config, lib, pkgs, ... }:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.fileMover;
in {
  options.services.luxnix.fileMover = {
    enable = mkBoolOpt false "Enable the move-my-files path-triggered service.";
  };

  config = mkIf cfg.enable {
    systemd.services.move-my-files = {
      description = "Move files from Source to Destination";
      serviceConfig = {
        Type = "oneshot";
        User = config.user.admin.name;
      };

      script = ''
        SOURCEVIDEO="/home/admin/video_import/"
        SOURCEREPORT="/home/admin/report_import/"
        DESTVIDEO="/home/admin/dev/lx-annotate/data/import/video_import/"
        DESTREPORT="/home/admin/dev/lx-annotate/data/import/report_import/"

        ${pkgs.coreutils}/bin/mkdir -p "$SOURCEVIDEO" "$SOURCEREPORT" "$DESTVIDEO" "$DESTREPORT"

        # We add a tiny sleep to ensure the file system settles if a file was JUST touched
        sleep 2

        # Run Rsync
        # We ignore errors so the service doesn't go into 'failed' state if a file is locked
        ${pkgs.rsync}/bin/rsync -av --remove-source-files --chmod=F660,D770 "$SOURCEVIDEO" "$DESTVIDEO" || true
        ${pkgs.rsync}/bin/rsync -av --remove-source-files --chmod=F660,D770 "$SOURCEREPORT" "$DESTREPORT" || true

        # Cleanup empty dirs
        ${pkgs.findutils}/bin/find "$SOURCEVIDEO" -mindepth 1 -type d -empty -delete
        ${pkgs.findutils}/bin/find "$SOURCEREPORT" -mindepth 1 -type d -empty -delete
      '';
    };

    # 2. The Path Watcher (REPLACES the timer)
    systemd.paths.move-my-files = {
      wantedBy = [ "paths.target" ];
      pathConfig = {
        # PathChanged triggers when a file is closed after writing (Safer for large videos)
        # PathModified triggers on every single write (Too noisy for videos)
        PathChanged = [
          "/home/admin/video_import/"
          "/home/admin/report_import/"
        ];
        Unit = "move-my-files.service";
      };
    };
  };
}
