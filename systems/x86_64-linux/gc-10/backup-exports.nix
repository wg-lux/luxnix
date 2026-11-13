# Host-only, explicitly authorized plaintext export copies; never import media or keys.
{ config, pkgs, ... }:
let
  backup = "/run/media/admin/Backup-24-11";
  uuid = "37bc8106-47d1-4963-ba25-9fd14b33db16";
  source = "${backup}/lx-annotate-exports";
  target = "/var/lib/lx-annotate/data/storage/frame_annotation_exports";
  backupUnit = "run-media-admin-Backup\\x2d24\\x2d11.mount";
  exportUnit = "var-lib-lx\\x2dannotate-data-storage-frame_annotation_exports";
  prepareUnit = "gc10-backup-exports-prepare.service";
in
{
  # Mount existing ext4 only: this drive is deliberately absent from disko.devices.
  fileSystems.${backup} = {
    device = "/dev/disk/by-uuid/${uuid}";
    fsType = "ext4";
    options = [
      "noauto"
      "nofail"
      "nodev"
      "nosuid"
      "noexec"
      "x-systemd.device-timeout=10s"
    ];
  };

  systemd = {
    services = {
      gc10-backup-exports-prepare = {
        description = "Verify gc-10 Backup identity before preparing its export directory";
        requires = [ backupUnit ];
        after = [ backupUnit ];
        bindsTo = [ backupUnit ];
        path = [
          pkgs.util-linux
          pkgs.coreutils
        ];
        serviceConfig.Type = "oneshot";
        script = ''
          set -euo pipefail
          actual_uuid=$(findmnt --noheadings --raw --mountpoint '${backup}' --output UUID)
          if [ "$actual_uuid" != '${uuid}' ]; then
            echo 'gc-10 export refused: Backup filesystem UUID does not match' >&2
            exit 1
          fi
          if [ -L '${source}' ]; then
            echo 'gc-10 export refused: export directory is a symlink' >&2
            exit 1
          fi
          # Group read lets nginx serve downloads via the X-Accel /protected_media/ alias.
          install -d -m 0750 -o '${config.user.endoreg-service-user.name}' \
            -g '${config.user.endoreg-service-user.group}' '${source}'
        '';
      };
      lx-annotate = {
        requires = [ "${exportUnit}.automount" ];
        after = [ "${exportUnit}.automount" ];
      };
      lx-annotate-celery-ffmpeg-worker = {
        requires = [ "${exportUnit}.automount" ];
        after = [ "${exportUnit}.automount" ];
      };
    };

    mounts = [
      {
        what = source;
        where = target;
        type = "none";
        options = "bind,nodev,nosuid,noexec";
        requires = [
          backupUnit
          prepareUnit
        ];
        after = [
          "local-fs.target"
          backupUnit
          prepareUnit
        ];
        bindsTo = [ backupUnit ];
        before = [ "umount.target" ];
        conflicts = [ "umount.target" ];
        unitConfig = {
          DefaultDependencies = false;
          RequiresMountsFor = [ "/var/lib/lx-annotate" ];
        };
        mountConfig.DirectoryMode = "0500";
      }
    ];

    # Access triggers the bind. An absent device fails the request instead of
    # exposing an ordinary writable export directory on the application disk.
    automounts = [
      {
        where = target;
        wantedBy = [ "multi-user.target" ];
        # The encrypted parent unlocks after local-fs.target. Default automount
        # ordering before that target would create a boot dependency cycle.
        after = [ "local-fs.target" ];
        before = [ "umount.target" ];
        conflicts = [ "umount.target" ];
        unitConfig = {
          DefaultDependencies = false;
          RequiresMountsFor = [ "/var/lib/lx-annotate" ];
        };
        automountConfig.DirectoryMode = "0500";
      }
    ];

  };
}
