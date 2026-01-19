{ config, lib, pkgs, ... }:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.fileMover;
  endoregPaths = config.roles.endoreg-client.paths;
  annotateCfg = config.services.luxnix.lxAnnotateLocal;

  endoregServiceUserName = config.user.endoreg-service-user.name;
  endoregServiceUserHome = config.users.users.${endoregServiceUserName}.home;
  repoDirName = "lx-annotate";
  repoDir = "${endoregServiceUserHome}/${repoDirName}";
  makeAbsolute = path: if lib.hasPrefix "/" path then path else "${repoDir}/${path}";
  dataDir = makeAbsolute annotateCfg.django.dataDir;
  
  sourceVideo = "${endoregPaths.videoInputDir}/";
  sourceReport = "${endoregPaths.pdfInputDir}/";
  destVideo = "${dataDir}/import/video_import/";
  destReport = "${dataDir}/import/report_import/";
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
        # We add a tiny sleep to ensure the file system settles if a file was JUST touched
        sleep 2

        # Run Rsync
        ${pkgs.rsync}/bin/rsync -av --remove-source-files --chmod=F660,D770 "${sourceVideo}" "${destVideo}" || echo "Warning: rsync video failed with exit code $?"
        ${pkgs.rsync}/bin/rsync -av --remove-source-files --chmod=F660,D770 "${sourceReport}" "${destReport}" || echo "Warning: rsync report failed with exit code $?"

        # Cleanup empty dirs
        ${pkgs.findutils}/bin/find "${sourceVideo}" -mindepth 1 -type d -empty -delete || true
        ${pkgs.findutils}/bin/find "${sourceReport}" -mindepth 1 -type d -empty -delete || true
      '';
    };
  };
}
