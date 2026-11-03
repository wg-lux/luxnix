{
  pkgs,
  repoRoot,
  ...
}:
let
  serviceUser = "endoreg-service-user";
  serviceGroup = "endoreg-service";
  postgresqlPackage = pkgs.postgresql_16;
  backupRoot = "/var/lib/lx-annotate-hub-backup-test";
  runtimeRoot = "${backupRoot}/runtime";
  incomingRoot = "${backupRoot}/incoming";
  snapshotRoot = "${backupRoot}/snapshots";
  manifestRoot = "${backupRoot}/manifests";
  postgresqlBackupRoot = "/var/backup/postgresql";
  mkHubBackupScripts =
    minimumFreeBytes:
    import "${repoRoot}/modules/nixos/services/lx-annotate-local/scripts/hub-backup.nix" {
      config = {
        networking.hostName = "hub-backup-vm";
        user.endoreg-service-user = {
          name = serviceUser;
          group = serviceGroup;
        };
        services.postgresql.package = postgresqlPackage;
        systemd.services.lx-annotate-test-writer.enable = true;
        systemd.timers = { };
      };
      cfg.runtime.encryptedDataDir = backupRoot;
      inherit (pkgs) lib;
      inherit pkgs;
      cfg.hub.backup = {
        sourceRuntimeDir = runtimeRoot;
        incomingDir = incomingRoot;
        snapshotDir = snapshotRoot;
        manifestDir = manifestRoot;
        retainCount = 2;
        inherit minimumFreeBytes;
        exclude = [ ];
      };
    };
  hubBackupScripts = mkHubBackupScripts 1;
  capacityBlockedHubBackupScripts = mkHubBackupScripts 999999999999999999;
in
{
  suites."lx-annotate hub backup" = {
    pos = __curPos;
    tests = [
      {
        name = "systemd-credential-couples-database-and-media-restore-point";
        type = "vm";
        vmConfig = {
          nodes.machine = {
            users.groups.${serviceGroup} = { };
            users.users.${serviceUser} = {
              isSystemUser = true;
              group = serviceGroup;
            };

            environment.systemPackages = [
              pkgs.coreutils
              pkgs.cryptsetup
              pkgs.e2fsprogs
              pkgs.util-linux
              pkgs.gzip
              pkgs.jq
              postgresqlPackage
              pkgs.rsync
            ];

            services.postgresql = {
              enable = true;
              package = postgresqlPackage;
            };

            systemd.packages = [ hubBackupScripts.hubBackupStartBarrier ];
            systemd = {
              tmpfiles.rules = [
                "d ${backupRoot} 0750 ${serviceUser} ${serviceGroup} - -"
                "d ${runtimeRoot} 0750 ${serviceUser} ${serviceGroup} - -"
                "d ${incomingRoot} 0750 ${serviceUser} ${serviceGroup} - -"
                "d ${snapshotRoot} 0750 ${serviceUser} ${serviceGroup} - -"
                "d ${manifestRoot} 0750 ${serviceUser} ${serviceGroup} - -"
                "d ${postgresqlBackupRoot} 0700 postgres postgres - -"
              ];

              services = {
                lx-annotate-test-writer = {
                  serviceConfig = {
                    ExecStart = "${pkgs.coreutils}/bin/sleep infinity";
                    ExecStop = pkgs.writeShellScript "finish-synthetic-writer" ''
                      set -eu
                      printf '%s' stopped-media > ${runtimeRoot}/stopped-media.bin
                      chown ${serviceUser}:${serviceGroup} ${runtimeRoot}/stopped-media.bin
                      chmod 0640 ${runtimeRoot}/stopped-media.bin
                      ${pkgs.util-linux}/bin/runuser -u postgres -- ${postgresqlPackage}/bin/psql \
                        --dbname hub_restore_test --set ON_ERROR_STOP=1 \
                        --command "UPDATE transfer_ledger SET resource_hash = 'stopped-media.bin';"
                      rm -f ${runtimeRoot}/processed-media.bin
                    '';
                  };
                };
                hub-coordinated-backup = {
                  serviceConfig = {
                    Type = "oneshot";
                    Group = serviceGroup;
                    RuntimeDirectory = "luxnix-hub-backup";
                    RuntimeDirectoryMode = "0710";
                    RuntimeDirectoryPreserve = "yes";
                    ExecStart = "${hubBackupScripts.hubBackupCoordinator}/bin/luxnix-hub-backup capture";
                    ExecStopPost = "${hubBackupScripts.hubBackupCoordinator}/bin/luxnix-hub-backup recover";
                  };
                };
                hub-coordinated-capacity-blocked = {
                  serviceConfig = {
                    Type = "oneshot";
                    Group = serviceGroup;
                    RuntimeDirectory = "luxnix-hub-backup";
                    RuntimeDirectoryMode = "0710";
                    RuntimeDirectoryPreserve = "yes";
                    ExecStart = "${capacityBlockedHubBackupScripts.hubBackupCoordinator}/bin/luxnix-hub-backup capture";
                    ExecStopPost = "${capacityBlockedHubBackupScripts.hubBackupCoordinator}/bin/luxnix-hub-backup recover";
                  };
                };
                hub-backup-test-media = {
                  description = "Provision an anonymized processed-media fixture";
                  wantedBy = [ "multi-user.target" ];
                  before = [ "lx-annotate-hub-backup.service" ];
                  serviceConfig = {
                    Type = "oneshot";
                    RemainAfterExit = true;
                    User = serviceUser;
                    Group = serviceGroup;
                    ExecStart = pkgs.writeShellScript "provision-hub-backup-test-media" ''
                      set -eu
                      printf '%s' anonymized-processed-media > ${runtimeRoot}/processed-media.bin
                      chmod 0640 ${runtimeRoot}/processed-media.bin
                    '';
                  };
                };

                hub-backup-test-database = {
                  description = "Provision a PostgreSQL transfer-ledger fixture";
                  wantedBy = [ "multi-user.target" ];
                  after = [ "postgresql.service" ];
                  requires = [ "postgresql.service" ];
                  before = [ "postgresqlBackup.service" ];
                  serviceConfig = {
                    Type = "oneshot";
                    RemainAfterExit = true;
                    User = "postgres";
                    ExecStart = pkgs.writeShellScript "provision-hub-backup-test-database" ''
                      set -eu
                      ${postgresqlPackage}/bin/createdb hub_restore_test
                      ${postgresqlPackage}/bin/psql \
                        --dbname hub_restore_test \
                        --set ON_ERROR_STOP=1 \
                        --command "CREATE TABLE transfer_ledger (transfer_key text PRIMARY KEY, resource_hash text NOT NULL, acknowledgement text NOT NULL); INSERT INTO transfer_ledger VALUES ('restore-transfer-1', 'sha256:restored-media', 'applied');"
                    '';
                  };
                };

                postgresqlBackup = {
                  description = "Produce a root-protected PostgreSQL dump";
                  after = [ "hub-backup-test-database.service" ];
                  requires = [ "hub-backup-test-database.service" ];
                  serviceConfig = {
                    Type = "oneshot";
                    User = "postgres";
                    ExecStart = pkgs.writeShellScript "produce-postgresql-backup-fixture" ''
                      set -eu
                      pending=${postgresqlBackupRoot}/all.in-progress.sql.gz
                      completed=${postgresqlBackupRoot}/all.sql.gz
                      if [ -e /run/hub-backup-corrupt-dump ]; then
                        printf '%s' not-a-gzip-dump > "$pending"
                      else
                        ${postgresqlPackage}/bin/pg_dumpall \
                          | ${pkgs.gzip}/bin/gzip -c > "$pending"
                      fi
                      chmod 0600 "$pending"
                      ${pkgs.coreutils}/bin/mv "$pending" "$completed"
                    '';
                  };
                };

                lx-annotate-hub-backup = {
                  description = "Create a coupled PostgreSQL and media restore point";
                  after = [
                    "hub-backup-test-media.service"
                    "postgresqlBackup.service"
                  ];
                  requires = [
                    "hub-backup-test-media.service"
                    "postgresqlBackup.service"
                  ];
                  serviceConfig = {
                    Type = "oneshot";
                    User = serviceUser;
                    Group = serviceGroup;
                    ExecStart = "${hubBackupScripts.runLocalHubBackupScript}/bin/runLxAnnotateHubBackup";
                    Environment = "HUB_BACKUP_EXCLUSIONS=[]";
                    LoadCredential = [
                      "hub-postgresql.sql.gz:${postgresqlBackupRoot}/all.sql.gz"
                    ];
                    PrivateTmp = true;
                    ProtectSystem = "full";
                    ReadWritePaths = [ backupRoot ];
                  };
                  path = [
                    pkgs.coreutils
                    pkgs.findutils
                    pkgs.gzip
                    pkgs.jq
                    pkgs.rsync
                  ];
                };

                lx-annotate-hub-backup-capacity-blocked = {
                  description = "Reject a hub restore point that would breach the free-space reserve";
                  after = [ "postgresqlBackup.service" ];
                  requires = [ "postgresqlBackup.service" ];
                  serviceConfig = {
                    Type = "oneshot";
                    User = serviceUser;
                    Group = serviceGroup;
                    ExecStart = "${capacityBlockedHubBackupScripts.runLocalHubBackupScript}/bin/runLxAnnotateHubBackup";
                    Environment = "HUB_BACKUP_EXCLUSIONS=[]";
                    LoadCredential = [
                      "hub-postgresql.sql.gz:${postgresqlBackupRoot}/all.sql.gz"
                    ];
                    PrivateTmp = true;
                    ProtectSystem = "full";
                    ReadWritePaths = [ backupRoot ];
                  };
                  path = [
                    pkgs.coreutils
                    pkgs.findutils
                    pkgs.gzip
                    pkgs.jq
                    pkgs.rsync
                  ];
                };
              };
            };
          };

          testScript = ''
            machine.wait_for_unit("multi-user.target")
            machine.wait_for_unit("postgresql.service")
            machine.wait_for_unit("hub-backup-test-database.service")
            machine.succeed("systemctl start lx-annotate-hub-backup.service")
            machine.succeed("test \"$(stat -c '%U:%G:%a' ${postgresqlBackupRoot}/all.sql.gz)\" = postgres:postgres:600")
            machine.succeed("readlink -f ${snapshotRoot}/latest > /run/first-hub-restore-point")
            machine.succeed("test -f ${snapshotRoot}/latest/database/all.sql.gz")
            machine.succeed("test -f ${snapshotRoot}/latest/processed-media.bin")
            machine.succeed("gzip -cd ${snapshotRoot}/latest/database/all.sql.gz | grep -F 'CREATE DATABASE hub_restore_test'")
            machine.succeed("grep -F anonymized-processed-media ${snapshotRoot}/latest/processed-media.bin")
            machine.succeed("jq -e '.database_dump.relative_path == \"database/all.sql.gz\" and .database_dump.format == \"postgresql-pg_dumpall-sql-gzip\"' ${manifestRoot}/*.json")
            machine.succeed("snapshot=$(readlink -f ${snapshotRoot}/latest); cd \"$snapshot\"; sha256sum --check ${manifestRoot}/$(basename \"$snapshot\").sha256")

            # Exercise the operator restore sequence against a real PostgreSQL
            # service and the media tree from the same published timestamp.
            machine.succeed("runuser -u postgres -- psql --dbname hub_restore_test --set ON_ERROR_STOP=1 --command \"UPDATE transfer_ledger SET resource_hash = 'sha256:mutated', acknowledgement = 'failed';\"")
            machine.succeed("printf '%s' mutated-media > ${runtimeRoot}/processed-media.bin")
            machine.succeed("snapshot=$(readlink -f ${snapshotRoot}/latest); cd \"$snapshot\"; sha256sum --check ${manifestRoot}/$(basename \"$snapshot\").sha256")
            machine.succeed("runuser -u postgres -- dropdb hub_restore_test")
            # A cluster-wide pg_dumpall necessarily recreates the postgres role.
            # This fixture restores into the same running test cluster, so allow
            # that expected role-exists error and verify the restored application
            # schema and data explicitly below.
            machine.succeed("gzip -cd ${snapshotRoot}/latest/database/all.sql.gz | runuser -u postgres -- psql --dbname postgres")
            machine.succeed("snapshot=$(readlink -f ${snapshotRoot}/latest); rsync --archive --delete --exclude database/ \"$snapshot/\" ${runtimeRoot}/")
            machine.succeed("test \"$(runuser -u postgres -- psql --dbname hub_restore_test --tuples-only --no-align --command \"SELECT transfer_key || '|' || resource_hash || '|' || acknowledgement FROM transfer_ledger;\")\" = 'restore-transfer-1|sha256:restored-media|applied'")
            machine.succeed("test \"$(cat ${runtimeRoot}/processed-media.bin)\" = anonymized-processed-media")
            machine.succeed("test \"$(stat -c '%U:%G:%a' ${runtimeRoot}/processed-media.bin)\" = ${serviceUser}:${serviceGroup}:640")

            machine.fail("systemctl start lx-annotate-hub-backup-capacity-blocked.service")
            machine.succeed("test \"$(readlink -f ${snapshotRoot}/latest)\" = \"$(cat /run/first-hub-restore-point)\"")
            machine.succeed("journalctl -u lx-annotate-hub-backup-capacity-blocked.service | grep -F 'free space is below the configured reserve before staging'")

            machine.succeed("touch /run/hub-backup-corrupt-dump")
            machine.fail("systemctl start lx-annotate-hub-backup.service")
            machine.succeed("test \"$(readlink -f ${snapshotRoot}/latest)\" = \"$(cat /run/first-hub-restore-point)\"")
            machine.succeed("test -z \"$(find ${snapshotRoot} -maxdepth 1 -name '.pending-*' -print -quit)\"")

            # Exercise the production coordinator with actual encrypted media,
            # PostgreSQL, systemd stop/start conditions and a fresh logical dump.
            machine.succeed("truncate -s 512M /var/lib/synthetic-backup.luks; printf test-key | cryptsetup luksFormat --batch-mode --type luks2 --key-file=- /var/lib/synthetic-backup.luks")
            machine.succeed("printf test-key | cryptsetup open --key-file=- /var/lib/synthetic-backup.luks backup-test; mkfs.ext4 /dev/mapper/backup-test; mount /dev/mapper/backup-test ${backupRoot}")
            machine.succeed("install -d -m 0750 -o ${serviceUser} -g ${serviceGroup} ${runtimeRoot} ${incomingRoot} ${snapshotRoot} ${manifestRoot}")
            machine.succeed("systemctl start lx-annotate-test-writer.service; systemctl start hub-coordinated-backup.service")
            machine.wait_for_unit("lx-annotate-test-writer.service")
            machine.succeed("test ! -e /run/luxnix-hub-backup/recovery.json; test ! -e /run/luxnix-hub-backup/quiescing; test ! -e /run/luxnix-hub-backup/capture/hub-postgresql.sql.gz")
            machine.succeed("test -f ${snapshotRoot}/latest/stopped-media.bin; test ! -e ${snapshotRoot}/latest/processed-media.bin")
            machine.succeed("runuser -u postgres -- dropdb hub_restore_test; gzip -cd ${snapshotRoot}/latest/database/all.sql.gz | runuser -u postgres -- psql --dbname postgres")
            machine.succeed("filename=$(runuser -u postgres -- psql --dbname hub_restore_test --tuples-only --no-align --command 'SELECT resource_hash FROM transfer_ledger'); test -f ${snapshotRoot}/latest/$filename")
            machine.succeed("readlink -f ${snapshotRoot}/latest > /run/coordinated-restore-point")
            machine.fail("systemctl start hub-coordinated-capacity-blocked.service")
            machine.wait_for_unit("lx-annotate-test-writer.service")
            machine.succeed("test \"$(readlink -f ${snapshotRoot}/latest)\" = \"$(cat /run/coordinated-restore-point)\"; test ! -e /run/luxnix-hub-backup/recovery.json")

          '';
        };
      }
    ];
  };
}
