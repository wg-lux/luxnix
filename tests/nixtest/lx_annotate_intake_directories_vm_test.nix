{
  pkgs,
  ...
}:
let
  serviceUser = "endoreg-service-user";
  serviceGroup = "endoreg-service";
  protectedDataRoot = "/var/lib/lx-annotate/data";
  intakeRoot = "${protectedDataRoot}/import";
  intakeDirectories = [
    "video_import"
    "report_import"
    "preanonymized_import"
    "sap_import"
    "sap_import_processed"
    "sap_import_failed"
  ];
  intakeTmpfilesRules = builtins.concatMap (directory: [
    "d ${intakeRoot}/${directory} 0770 ${serviceUser} ${serviceGroup} - -"
    "z ${intakeRoot}/${directory} 0770 ${serviceUser} ${serviceGroup} - -"
  ]) intakeDirectories;
in
{
  suites."lx-annotate intake directories" = {
    pos = __curPos;
    tests = [
      {
        name = "tmpfiles-provisions-protected-intake-tree-on-empty-volume";
        type = "vm";
        vmConfig = {
          nodes.machine = {
            users.groups.${serviceGroup} = { };
            users.users.${serviceUser} = {
              isSystemUser = true;
              group = serviceGroup;
            };

            fileSystems.${protectedDataRoot} = {
              device = "tmpfs";
              fsType = "tmpfs";
              options = [
                "mode=0750"
                "size=16M"
              ];
            };

            systemd.services.lx-annotate-intake-volume-empty = {
              description = "Assert lx-annotate intake volume starts empty";
              requiredBy = [ "systemd-tmpfiles-setup.service" ];
              before = [ "systemd-tmpfiles-setup.service" ];
              unitConfig.RequiresMountsFor = [ protectedDataRoot ];
              serviceConfig = {
                Type = "oneshot";
                ExecStart = pkgs.writeShellScript "assert-lx-annotate-intake-volume-empty" ''
                  set -eu
                  test ! -e ${intakeRoot}
                  touch /run/lx-annotate-intake-volume-was-empty
                '';
              };
            };

            systemd.tmpfiles.rules = [
              "d ${protectedDataRoot} 0750 ${serviceUser} ${serviceGroup} - -"
              "z ${protectedDataRoot} 0750 ${serviceUser} ${serviceGroup} - -"
              "d ${intakeRoot} 0770 ${serviceUser} ${serviceGroup} - -"
              "z ${intakeRoot} 0770 ${serviceUser} ${serviceGroup} - -"
            ]
            ++ intakeTmpfilesRules;
          };

          testScript = ''
            machine.wait_for_unit("systemd-tmpfiles-setup.service")
            machine.succeed("test -f /run/lx-annotate-intake-volume-was-empty")
            machine.succeed("mountpoint -q ${protectedDataRoot}")
            machine.succeed(
                "test \"$(stat -c '%U:%G:%a' ${intakeRoot})\" = "
                "\"${serviceUser}:${serviceGroup}:770\""
            )

            for directory in ${builtins.toJSON intakeDirectories}:
                path = "${intakeRoot}/" + directory
                machine.succeed("test -d " + path)
                machine.succeed(
                    "test \"$(stat -c '%U:%G:%a' "
                    + path
                    + ")\" = \"${serviceUser}:${serviceGroup}:770\""
                )
          '';
        };
      }
    ];
  };
}
