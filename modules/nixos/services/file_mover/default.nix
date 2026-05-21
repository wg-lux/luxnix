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

  defaultServiceUserName =
    if
      config ? user && config.user ? endoreg-service-user && config.user.endoreg-service-user ? name
    then
      config.user.endoreg-service-user.name
    else
      "endoreg-service-user";

  defaultServiceGroup =
    if
      config ? user && config.user ? endoreg-service-user && config.user.endoreg-service-user ? group
    then
      config.user.endoreg-service-user.group
    else
      "endoreg-service";

  configuredPathOrPlaceholder =
    name: path: if path == null then "/run/luxnix-file-mover-unconfigured/${name}" else path;

  sourceVideoDir = cfg.paths.sourceVideoDir;
  sourcePdfDir = cfg.paths.sourcePdfDir;
  failedVideoDir = cfg.paths.failedVideoDir;
  failedPdfDir = cfg.paths.failedPdfDir;
  destVideoDir = configuredPathOrPlaceholder "video-destination" cfg.paths.destinationVideoDir;
  destReportDir = configuredPathOrPlaceholder "report-destination" cfg.paths.destinationReportDir;
  runtimeMoverStagingDir = configuredPathOrPlaceholder "staging" cfg.paths.stagingDir;

  serviceUserName = cfg.serviceUserName;
  serviceGroup = cfg.serviceGroup;
  desktopLinkNames = lib.attrNames cfg.desktop.links;
  desktopUsers = lib.unique cfg.desktop.users;
  fileMoverRuntimePath = lib.makeBinPath cfg.runtimePathPackages;
  videoTranscodeCommand =
    if cfg.videoTranscodeFallback.command == null then "" else cfg.videoTranscodeFallback.command;
  videoTranscodeWorkingDir = cfg.videoTranscodeFallback.workingDir;

  prepareDesktopLinksActivation = lib.optionalString (desktopLinkNames != [ ]) ''
    desktop_dir="$HOME/${cfg.desktop.dirName}"

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

    serviceUserName = mkOption {
      type = types.str;
      default = defaultServiceUserName;
      description = "User that runs the file mover worker.";
    };

    serviceGroup = mkOption {
      type = types.str;
      default = defaultServiceGroup;
      description = "Group used for moved files and shared input access.";
    };

    runtimePathPackages = mkOption {
      type = types.listOf types.package;
      default = [
        pkgs.coreutils
        pkgs.findutils
        pkgs.ffmpeg
        pkgs.gnugrep
        pkgs.gnused
      ];
      description = "Packages added to PATH for the mover and optional video fallback hook.";
    };

    paths = mkOption {
      type = types.submodule {
        options = {
          sourceVideoDir = mkOption {
            type = types.str;
            default = toString endoregPaths.videoInputDir;
            description = "Directory watched for operator video drops.";
          };

          sourcePdfDir = mkOption {
            type = types.str;
            default = toString endoregPaths.pdfInputDir;
            description = "Directory watched for operator PDF drops.";
          };

          failedVideoDir = mkOption {
            type = types.str;
            default = "${endoregPaths.storageBaseDir}/failed_input/video";
            description = "Quarantine directory for unreadable video input.";
          };

          failedPdfDir = mkOption {
            type = types.str;
            default = "${endoregPaths.storageBaseDir}/failed_input/pdf";
            description = "Quarantine directory for unreadable PDF input.";
          };

          destinationVideoDir = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Directory where validated video entries are published.";
          };

          destinationReportDir = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Directory where validated report/PDF entries are published.";
          };

          stagingDir = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Private staging directory used before entries are published into destination directories.";
          };
        };
      };
      default = { };
      description = "Source, destination, staging, and quarantine paths for move-my-files.";
    };

    desktop = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Create desktop symlinks for configured file mover paths.";
          };

          dirName = mkOption {
            type = types.str;
            default = config.roles.endoreg-client.paths.desktopDirName;
            description = "Desktop directory name used for Home Manager links.";
          };

          users = mkOption {
            type = types.listOf types.str;
            default = lib.unique [
              clientUserName
              adminUserName
            ];
            description = "Home Manager users that receive file mover desktop links.";
          };

          links = mkOption {
            type = types.attrsOf types.str;
            default = { };
            description = "Desktop link name to out-of-store target path mappings.";
          };
        };
      };
      default = { };
      description = "Desktop integration for file mover input paths.";
    };

    videoTranscodeFallback = mkOption {
      type = types.submodule {
        options = {
          command = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Optional shell command for video fallback processing. It is invoked with input directory, input filename, and output directory as positional arguments.";
          };

          workingDir = mkOption {
            type = types.str;
            default = "/";
            description = "Working directory used when running the video fallback command.";
          };

          environmentScript = mkOption {
            type = types.lines;
            default = "";
            description = "Shell snippet that exports environment required by the video fallback command.";
          };

          timeoutSeconds = mkOption {
            type = types.str;
            default = "86400";
            description = "FFmpeg timeout value exported for fallback video processing.";
          };
        };
      };
      default = { };
      description = "Optional video processing fallback used when direct video publishing is not enough.";
    };
  };

  config = mkIf cfg.enable (mkMerge [
    {
      services.luxnix.fileMover.desktop.links = {
        Video_Input = mkDefault sourceVideoDir;
        PDF_Input = mkDefault sourcePdfDir;
      };
    }
    {
      assertions = [
        {
          assertion = cfg.paths.destinationVideoDir != null;
          message = "services.luxnix.fileMover.paths.destinationVideoDir must be configured when fileMover is enabled.";
        }
        {
          assertion = cfg.paths.destinationReportDir != null;
          message = "services.luxnix.fileMover.paths.destinationReportDir must be configured when fileMover is enabled.";
        }
        {
          assertion = cfg.paths.stagingDir != null;
          message = "services.luxnix.fileMover.paths.stagingDir must be configured when fileMover is enabled.";
        }
      ];

      # 1. Ensure directories exist (Source & Dest)
      systemd.tmpfiles.rules = [
        "d \"${sourceVideoDir}\" 0770 root ${serviceGroup} -"
        "d \"${sourcePdfDir}\" 0770 root ${serviceGroup} -"
        "d \"${failedVideoDir}\" 0770 root ${serviceGroup} -"
        "d \"${failedPdfDir}\" 0770 root ${serviceGroup} -"
        "d \"${runtimeMoverStagingDir}\" 0770 ${serviceUserName} ${serviceGroup} -"
        "d \"${destVideoDir}\" 0770 ${serviceUserName} ${serviceGroup} -"
        "d \"${destReportDir}\" 0770 ${serviceUserName} ${serviceGroup} -"
      ];

      # 2. Home Manager: create operator-facing desktop links.
      home-manager.users = mkIf (cfg.desktop.enable && cfg.desktop.links != { } && desktopUsers != [ ]) (
        lib.genAttrs desktopUsers (
          userName:
          { config, lib, ... }:
          let
            outOfStore = config.lib.file.mkOutOfStoreSymlink;
          in
          {
            xdg.userDirs = {
              enable = true;
              createDirectories = true;
              extraConfig = {
                XDG_DESKTOP_DIR = "${config.home.homeDirectory}/${cfg.desktop.dirName}";
              };
            };

            home.file = lib.mapAttrs' (
              linkName: targetPath:
              lib.nameValuePair "${cfg.desktop.dirName}/${linkName}" {
                source = outOfStore targetPath;
              }
            ) cfg.desktop.links;

            home.activation.prepareFileMoverDesktopLinks = lib.hm.dag.entryBefore [
              "checkLinkTargets"
            ] prepareDesktopLinksActivation;
          }
        )
      );

      # 3. The Worker Service
      systemd.services.move-my-files = {
        description = "Move files from Source to Destination";
        serviceConfig = {
          Type = "oneshot";
          User = serviceUserName;
          Group = serviceGroup;
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
              ${pkgs.coreutils}/bin/install -d -m 2770 -o root -g ${serviceGroup} "$dir"
            done

            normalize_tree_permissions() {
              local source_dir="$1"
              ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type l -exec ${pkgs.coreutils}/bin/chgrp -h ${serviceGroup} {} + || true
              ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 ! -type l ! -group ${serviceGroup} -exec ${pkgs.coreutils}/bin/chgrp ${serviceGroup} {} + || true
              ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type d \( ! -perm -2070 -o -perm /0007 \) -exec ${pkgs.coreutils}/bin/chmod g+rws,o-rwx {} + || true
              ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f \( ! -perm -0060 -o -perm /0007 \) -exec ${pkgs.coreutils}/bin/chmod g+rw,o-rwx {} + || true
            }

            normalize_tree_permissions "${sourceVideoDir}"
            normalize_tree_permissions "${sourcePdfDir}"
          ''}";
        };

        script = ''
          set -euo pipefail

          # Safety check: Ensure destinations exist.
          mkdir -p "${destVideoDir}" "${destReportDir}" "${failedVideoDir}" "${failedPdfDir}" "${runtimeMoverStagingDir}"

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

            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type l -exec ${pkgs.coreutils}/bin/chgrp -h ${serviceGroup} {} + || true
            ${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 ! -type l ! -group ${serviceGroup} -exec ${pkgs.coreutils}/bin/chgrp ${serviceGroup} {} + || true
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
                echo "Waiting: video input is not readable by ${serviceUserName} after permission normalization: $video_file"
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

          export_video_transcode_fallback_env() {
            export PATH="${fileMoverRuntimePath}:''${PATH:-}"
            export FFMPEG_TRANSCODE_TIMEOUT_SECONDS="${cfg.videoTranscodeFallback.timeoutSeconds}"
            ${cfg.videoTranscodeFallback.environmentScript}
          }

          transcode_video_entry() {
            local input_file="$1"
            local dest_dir="$2"
            local entry_name="$3"
            local input_dir=""
            local output_file=""
            local output_name=""

            if ! is_video_filename "$entry_name"; then
              return 1
            fi

            if [ -z ${lib.escapeShellArg videoTranscodeCommand} ]; then
              echo "Warning: Video publish failed, but no video transcode fallback command is configured."
              return 1
            fi

            input_dir="$(${pkgs.coreutils}/bin/dirname "$input_file")"
            output_name="''${entry_name%.*}.mp4"
            output_file="''${dest_dir}/''${output_name}"
            export_video_transcode_fallback_env

            echo "Warning: Direct video publish failed; trying transcode fallback to system standard: $input_file -> $output_file"
            if ! (
              cd "${videoTranscodeWorkingDir}"
              "${pkgs.bash}/bin/bash" -lc ${lib.escapeShellArg videoTranscodeCommand} file-mover-transcode "$input_dir" "$entry_name" "$dest_dir"
            ); then
              ${pkgs.coreutils}/bin/rm -f "$output_file" || true
              echo "Warning: video transcode fallback command failed for $input_file"
              return 1
            fi

            if [ ! -s "$output_file" ]; then
              ${pkgs.coreutils}/bin/rm -f "$output_file" || true
              echo "Warning: video transcode fallback did not create a non-empty output file: $output_file"
              return 1
            fi

            if ! ${pkgs.coreutils}/bin/chgrp ${serviceGroup} "$output_file"; then
              ${pkgs.coreutils}/bin/rm -f "$output_file" || true
              echo "Warning: failed to set group on transcoded Video entry: $output_file"
              return 1
            fi

            if ! ${pkgs.coreutils}/bin/chmod 0660 "$output_file"; then
              ${pkgs.coreutils}/bin/rm -f "$output_file" || true
              echo "Warning: failed to set mode on transcoded Video entry: $output_file"
              return 1
            fi

            ${pkgs.coreutils}/bin/rm -f "$input_file" || true
            echo "Published transcoded Video entry: $output_file"
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
              echo "Warning: ''${label} file unreadable by ${serviceUserName}. Quarantining: $unreadable_file"

              if ! ${pkgs.coreutils}/bin/mv -f "$unreadable_file" "$quarantine_target"; then
                echo "Warning: Failed to quarantine unreadable file: $unreadable_file"
                overall_status=1
              fi
            done < <(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type f ! -readable -print0)
          }

          quarantine_symlink_entries() {
            local source_dir="$1"
            local quarantine_dir="$2"
            local label="$3"

            while IFS= read -r -d "" symlink_entry; do
              base_name="$(${pkgs.coreutils}/bin/basename "$symlink_entry")"
              timestamp="$(${pkgs.coreutils}/bin/date +%Y%m%d-%H%M%S)"
              quarantine_target="''${quarantine_dir}/''${timestamp}-''${base_name}"
              echo "Warning: ''${label} input is a symlink. Quarantining instead of dereferencing: $symlink_entry"

              if ! ${pkgs.coreutils}/bin/mv -f "$symlink_entry" "$quarantine_target"; then
                echo "Warning: Failed to quarantine symlink input: $symlink_entry"
                overall_status=1
              fi
            done < <(${pkgs.findutils}/bin/find "$source_dir" -mindepth 1 -type l -print0)
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
            quarantine_symlink_entries "$source_dir" "$quarantine_dir" "$label"
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
            ${pkgs.coreutils}/bin/install -d -m 0770 -o ${serviceUserName} -g ${serviceGroup} "$staging_dir" "$dest_dir"

            if ! ${pkgs.rsync}/bin/rsync -av --omit-dir-times --chmod=F660,D770 --chown=${serviceUserName}:${serviceGroup} "''${source_dir}/" "''${staging_dir}/"; then
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
    }
  ]);
}
