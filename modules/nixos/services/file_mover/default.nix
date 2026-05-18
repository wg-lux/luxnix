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
  repoDir = "${endoreg-service-user-home}/${repoDirName}";
  lxAnnotateUseWheelRuntime = lxAnnotateCfg.runtime.mode == "wheel";
  lxAnnotateWheelRootPath = "${endoreg-service-user-home}/lx-annotate-wheel";
  lxAnnotateWheelVenvPath = "${lxAnnotateWheelRootPath}/.venv";
  lxAnnotateRuntimeWorkingDir =
    if lxAnnotateUseWheelRuntime then lxAnnotateWheelRootPath else repoDir;
  lxAnnotateConfDir =
    if lxAnnotateUseWheelRuntime then
      "${lxAnnotateWheelRootPath}/${lxAnnotateCfg.django.confDir}"
    else
      "${repoDir}/${lxAnnotateCfg.django.confDir}";
  lxAnnotateTranscodeVideoCommand =
    if lxAnnotateUseWheelRuntime then
      lxAnnotateCfg.runtime.commands.transcodeVideo or ""
    else
      "python manage.py transcode_video";
  lxAnnotateTranscodeVideoCommandWithArgs = "${lxAnnotateTranscodeVideoCommand} --input-dir \"$1\" --filename \"$2\" --output-dir \"$3\" --overwrite --json";
  fileMoverRuntimePath = lib.makeBinPath [
    pkgs.coreutils
    pkgs.findutils
    pkgs.ffmpeg
    pkgs.gnugrep
    pkgs.gnused
  ];
  ffmpegTranscodeTimeoutSeconds = "86400";

  # Source paths
  sourceVideoDir = endoregPaths.videoInputDir;
  sourcePdfDir = endoregPaths.pdfInputDir;
  failedInputBaseDir = "${endoregPaths.storageBaseDir}/failed_input";
  failedVideoDir = "${failedInputBaseDir}/video";
  failedPdfDir = "${failedInputBaseDir}/pdf";
  runtimeDataDir = lxAnnotateCfg.runtime.encryptedDataDir;
  intakeDirs = lxAnnotateCfg.runtime.intakeDirs;
  resolveRuntimeDataPath =
    path:
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

          home.activation.prepareFileMoverDesktopLinks = lib.hm.dag.entryBefore [
            "checkLinkTargets"
          ] prepareDesktopLinksActivation;
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

          home.activation.prepareFileMoverDesktopLinks = lib.hm.dag.entryBefore [
            "checkLinkTargets"
          ] prepareDesktopLinksActivation;
        };
    };

    # 3. The Worker Service
    systemd.services.move-my-files = {
      description = "Move files from Source to Destination";
      serviceConfig = {
        Type = "oneshot";
        User = endoregServiceUserName;
        Group = endoregServiceGroup;
        TimeoutStartSec = "2h";
        # Files moved into the source dirs while the service is already running
        # can keep operator ownership/modes; the wait loop repairs that in place.
        CapabilityBoundingSet = [
          "CAP_CHOWN"
          "CAP_FOWNER"
        ];
        AmbientCapabilities = [
          "CAP_CHOWN"
          "CAP_FOWNER"
        ];
        # ExecStartPre runs as root and normalizes source permissions before rsync.
        PermissionsStartOnly = true;
        ExecStartPre = "${pkgs.writeShellScript "move-my-files-prepare-inputs" ''
          set -euo pipefail

          for dir in "${sourceVideoDir}" "${sourcePdfDir}" "${failedVideoDir}" "${failedPdfDir}"; do
            ${pkgs.coreutils}/bin/install -d -m 2770 -o root -g ${endoregServiceGroup} "$dir"
          done

          normalize_tree_permissions() {
            local source_dir="$1"
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 ! -group ${endoregServiceGroup} -exec ${pkgs.coreutils}/bin/chgrp ${endoregServiceGroup} {} + || true
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type d \( ! -perm -2070 -o -perm /0007 \) -exec ${pkgs.coreutils}/bin/chmod g+rws,o-rwx {} + || true
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f \( ! -perm -0060 -o -perm /0007 \) -exec ${pkgs.coreutils}/bin/chmod g+rw,o-rwx {} + || true
          }

          normalize_tree_permissions "${sourceVideoDir}"
          normalize_tree_permissions "${sourcePdfDir}"
        ''}";
      };

      script = ''
        set -euo pipefail

        # Safety check: Ensure destination exists (repository might have just finished cloning)
        mkdir -p "${destVideoDir}" "${destReportDir}" "${failedVideoDir}" "${failedPdfDir}"

        overall_status=0

        source_has_files() {
          local source_dir="$1"
          [ -n "$(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f -print -quit)" ]
        }

        is_video_filename() {
          local file_name="''${1,,}"
          case "$file_name" in
            *.avi|*.m4v|*.mkv|*.mov|*.mp4|*.mpeg|*.mpg|*.webm) return 0 ;;
            *) return 1 ;;
          esac
        }

        normalize_source_permissions() {
          local source_dir="$1"

          ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 ! -group ${endoregServiceGroup} -exec ${pkgs.coreutils}/bin/chgrp ${endoregServiceGroup} {} + || true
          ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type d \( ! -perm -2070 -o -perm /0007 \) -exec ${pkgs.coreutils}/bin/chmod g+rws,o-rwx {} + || true
          ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f \( ! -perm -0060 -o -perm /0007 \) -exec ${pkgs.coreutils}/bin/chmod g+rw,o-rwx {} + || true
        }

        newest_source_ctime_epoch() {
          local source_dir="$1"
          ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f -printf '%C@\n' \
            | ${pkgs.coreutils}/bin/sort -nr \
            | ${pkgs.coreutils}/bin/head -n 1 \
            | ${pkgs.coreutils}/bin/cut -d. -f1
        }

        snapshot_source_files() {
          local source_dir="$1"
          ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f -printf '%P\n' \
            | ${pkgs.coreutils}/bin/sort \
            | while IFS= read -r relative_path; do
                ${pkgs.coreutils}/bin/stat -c '%n:%s:%Z' "$source_dir/$relative_path"
              done
        }

        validate_video_sources() {
          local source_dir="$1"
          local validation_status=0
          local ffprobe_error=""
          local ffprobe_error_summary=""

          while IFS= read -r -d "" video_file; do
            if [ ! -r "$video_file" ]; then
              echo "Waiting: video input is not readable by ${endoregServiceUserName} after permission normalization: $video_file"
              validation_status=2
              continue
            fi

            if ! ffprobe_error="$(${pkgs.ffmpeg}/bin/ffprobe -v error -show_entries format=format_name,duration -of default=noprint_wrappers=1 "$video_file" 2>&1 >/dev/null)"; then
              ffprobe_error_summary="$(${pkgs.coreutils}/bin/printf '%s\n' "$ffprobe_error" | ${pkgs.coreutils}/bin/head -n 1)"
              if [ -n "$ffprobe_error_summary" ]; then
                echo "Waiting: video input is readable but ffprobe rejected it: $video_file ($ffprobe_error_summary)"
              else
                echo "Waiting: video input is readable but ffprobe rejected it without details: $video_file"
              fi
              if [ "$validation_status" -eq 0 ]; then
                validation_status=1
              fi
            fi
          done < <(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f \( -iname '*.avi' -o -iname '*.m4v' -o -iname '*.mkv' -o -iname '*.mov' -o -iname '*.mp4' -o -iname '*.webm' \) -print0)

          return "$validation_status"
        }

        export_lx_annotate_transcode_env() {
          local db_pwd=""
          local django_secret_key=""
          local oidc_client_secret=""

          export PATH="${fileMoverRuntimePath}:''${PATH:-}"
          export LX_ANNOTATE_WHEEL_VENV="${lxAnnotateWheelVenvPath}"
          export LX_ANNOTATE_WHEEL_APP_ROOT="${lxAnnotateWheelRootPath}"
          export DJANGO_SETTINGS_MODULE="lx_annotate.settings.settings_prod"
          export DJANGO_SETTINGS_MODULE_PRODUCTION="lx_annotate.settings.settings_prod"
          export DJANGO_ENV="production"
          export DATA_DIR="${runtimeDataDir}"
          export LX_ANNOTATE_DATA_DIR="${runtimeDataDir}"
          export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${runtimeDataDir}"
          export PROTECTED_MEDIA_ROOT="${runtimeDataDir}/storage"
          export STORAGE_DIR="${runtimeDataDir}/storage"
          export WATCHER_VIDEO_DIR="${destVideoDir}"
          export WATCHER_REPORT_DIR="${destReportDir}"
          export WATCHER_PREANONYMIZED_DIR="${runtimePreanonymizedDir}"
          export FFMPEG_TRANSCODE_TIMEOUT_SECONDS="${ffmpegTranscodeTimeoutSeconds}"
          export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
          export REQUESTS_CA_BUNDLE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"

          export DJANGO_SECRET_KEY_FILE="${toString lxAnnotateCfg.django.djangoSecretKeyFile}"
          django_secret_key="$(${pkgs.coreutils}/bin/tr -d '\n' < "${toString lxAnnotateCfg.django.djangoSecretKeyFile}" 2>/dev/null || true)"
          export DJANGO_SECRET_KEY="$django_secret_key"

          export CONF_DIR="${lxAnnotateConfDir}"
          export DB_PWD_FILE="${lxAnnotateConfDir}/db_pwd"
          export DJANGO_DB_PASSWORD_FILE="${lxAnnotateConfDir}/db_pwd"
          db_pwd="$(${pkgs.coreutils}/bin/tr -d '\n' < "${lxAnnotateConfDir}/db_pwd" 2>/dev/null || true)"
          export DJANGO_DB_ENGINE="django.db.backends.postgresql"
          export DJANGO_DB_NAME="${lxAnnotateCfg.database.name}"
          export DJANGO_DB_USER="${lxAnnotateCfg.database.user}"
          export DJANGO_DB_PASSWORD="$db_pwd"
          export DJANGO_DB_HOST="${lxAnnotateCfg.database.host}"
          export DJANGO_DB_PORT="${toString lxAnnotateCfg.database.port}"
          export DJANGO_DB_SSLMODE="${lxAnnotateCfg.database.sslMode}"

          export DJANGO_ALLOWED_HOSTS="${lib.concatStringsSep "," lxAnnotateCfg.django.djangoAllowedHosts}"
          export ALLOWED_HOSTS="${lib.concatStringsSep "," lxAnnotateCfg.django.djangoAllowedHosts}"
          export DJANGO_CORS_ALLOWED_ORIGINS="${lib.concatStringsSep "," lxAnnotateCfg.django.corsAllowedOrigins}"
          export DJANGO_CSRF_TRUSTED_ORIGINS="${lib.concatStringsSep "," lxAnnotateCfg.django.corsAllowedOrigins}"
          export OIDC_RP_CLIENT_ID="${lxAnnotateCfg.django.keycloakClientId}"
          oidc_client_secret="$(${pkgs.coreutils}/bin/tr -d '\n' < "${toString lxAnnotateCfg.django.keycloakSecretFile}" 2>/dev/null || true)"
          export OIDC_RP_CLIENT_SECRET="$oidc_client_secret"
        }

        transcode_video_entry() {
          local input_file="$1"
          local dest_dir="$2"
          local entry_name="$3"
          local input_dir=""
          local output_name=""

          if ! is_video_filename "$entry_name"; then
            return 1
          fi

          if [ -z ${lib.escapeShellArg lxAnnotateTranscodeVideoCommand} ]; then
            echo "Warning: Video publish failed, but no lx-annotate transcode command is configured."
            return 1
          fi

          input_dir="$(${pkgs.coreutils}/bin/dirname "$input_file")"
          output_name="''${entry_name%.*}.mp4"
          export_lx_annotate_transcode_env

          echo "Warning: Direct video publish failed; trying transcode fallback to system standard: $input_file -> ''${dest_dir}/''${output_name}"
          (
            cd "${lxAnnotateRuntimeWorkingDir}"
            "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg lxAnnotateTranscodeVideoCommandWithArgs} lx-annotate-transcode "$input_dir" "$entry_name" "$dest_dir"
          )

          ${pkgs.coreutils}/bin/chgrp ${endoregServiceGroup} "''${dest_dir}/''${output_name}" || true
          ${pkgs.coreutils}/bin/chmod 0660 "''${dest_dir}/''${output_name}" || true
          ${pkgs.coreutils}/bin/rm -f "$input_file" || true
          echo "Published transcoded Video entry: ''${dest_dir}/''${output_name}"
        }

        wait_for_input_ready() {
          local source_dir="$1"
          local label="$2"
          local interval_seconds=10
          local min_age_seconds=60
          local required_stable_checks=3
          local max_wait_seconds=7200
          local elapsed_seconds=0
          local stable_checks=0
          local previous_snapshot=""
          local current_snapshot=""
          local newest_ctime=""
          local newest_age=0
          local now_epoch=0
          local video_validation_status=0

          while [ "$elapsed_seconds" -le "$max_wait_seconds" ]; do
            normalize_source_permissions "$source_dir"

            if ! source_has_files "$source_dir"; then
              return 0
            fi

            if ! current_snapshot="$(snapshot_source_files "$source_dir")"; then
              current_snapshot=""
            fi

            newest_ctime="$(newest_source_ctime_epoch "$source_dir" || true)"
            now_epoch="$(${pkgs.coreutils}/bin/date +%s)"
            newest_age=0
            if [ -n "$newest_ctime" ]; then
              newest_age=$((now_epoch - newest_ctime))
            fi

            if [ "$current_snapshot" = "$previous_snapshot" ] && [ "$newest_age" -ge "$min_age_seconds" ]; then
              stable_checks=$((stable_checks + 1))
            else
              stable_checks=0
            fi

            if [ "$stable_checks" -ge "$required_stable_checks" ]; then
              if [ "$label" != "Video" ]; then
                return 0
              fi

              if validate_video_sources "$source_dir"; then
                return 0
              else
                video_validation_status="$?"
                if [ "$video_validation_status" -eq 2 ]; then
                  echo "Warning: Video input is stable but still unreadable after permission normalization. Leaving files in place for a later retry."
                  return 1
                fi
              fi
            fi

            echo "Waiting for ''${label} input to settle: age=''${newest_age}s, stable_checks=''${stable_checks}/''${required_stable_checks}"
            previous_snapshot="$current_snapshot"
            sleep "$interval_seconds"
            elapsed_seconds=$((elapsed_seconds + interval_seconds))
          done

          echo "Warning: ''${label} input did not become ready within ''${max_wait_seconds}s. Leaving files in place for a later retry."
          return 1
        }

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
          normalize_source_permissions "$source_dir"
          quarantine_unreadable_files "$source_dir" "$quarantine_dir" "$label"

          # If everything was quarantined, there's nothing left to sync.
          if [ -z "$(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -print -quit)" ]; then
            return 0
          fi

          if ! wait_for_input_ready "$source_dir" "$label"; then
            overall_status=1
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
            if [ "$label" = "Video" ] && is_video_filename "$entry_name"; then
              if transcode_video_entry "$staged_entry" "$dest_dir" "$entry_name"; then
                continue
              fi
              echo "Warning: failed to transcode staged Video entry: $staged_entry"
              publish_status=1
              overall_status=1
              continue
            fi

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
