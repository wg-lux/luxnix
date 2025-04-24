{ pkgs
, config
, lib
, ...
}:
with lib;
with lib.luxnix; let
  srcVaultDir = "/etc/secrets/vault";
  maintenanceSecretFileName = "SCRT_local_password_maintenance_password";
  cfg = config.user.endoreg-service-user;
  homeDir = "/var/${cfg.name}";
  endoreg-service-user-name = cfg.name;
  endoreg-service-group-name = "endoreg-service";
  vaultDirAbsolute = "${homeDir}/${cfg.vaultDir}";
  maintenanceSecretFileSource = "${srcVaultDir}/${maintenanceSecretFileName}";
  maintenanceSecretFilePath = "${vaultDirAbsolute}/${maintenanceSecretFileName}";

  endoregServiceUserDeployMaintenanceSecretFile = pkgs.writeShellScriptBin "endoreg-service-user-deploy-maintenance-secretfile" ''
    cp ${maintenanceSecretFileSource} ${maintenanceSecretFilePath}
    chown ${endoreg-service-user-name}:${endoreg-service-group-name} ${maintenanceSecretFilePath}
    chmod 0400 ${maintenanceSecretFilePath}
  '';

in
{
  options.user.endoreg-service-user = with types; {
    name = mkOpt str "endoreg-service-user" "The name of the user's account";
    enable = mkBoolOpt false "Enable the user";
    group = mkOpt str endoreg-service-group-name "The name of the user's group. DONT CHANGE";
    vaultDir = mkOption {
      type = str;
      default = "secrets/vault";
      description = "The directory where the secret files are stored";
    };
    extraGroups = mkOpt (listOf str) [ ] "Groups for the user to be assigned.";
    extraOptions =
      mkOpt attrs { }
        "Extra options passed to users.users.<name>";
  };

  config = mkIf cfg.enable {
    systemd.tmpfiles.rules = [
      "d /var/${cfg.name} 0750 ${cfg.name} ${cfg.group} -"
      "d /var/${cfg.name}/secrets 0750 ${cfg.name} ${cfg.group} -"
      "d ${vaultDirAbsolute} 0750 ${cfg.name} ${cfg.group} -"
    ];
    users.users.${cfg.name} =
      {
        shell = pkgs.zsh;
        isSystemUser = true;
        createHome = true;
        home = "${homeDir}";
        group = "${cfg.group}";
        homeMode = "0750";
        uid = 400;

        # TODO: set in modules
        extraGroups =
          [
          ]
          ++ cfg.extraGroups;
      }
      // cfg.extraOptions;

    # service to deploy secretfile
    systemd.services."endoreg-service-user-deploy-secretfile-postgres" = {
      description = "Deploy secretfile";
      wantedBy = [ "multi-user.target" ];
      after = [ "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "oneshot";
        User = "root";
        Environment = "PATH=/run/current-system/sw/bin";
        ExecStart = "${endoregServiceUserDeployMaintenanceSecretFile}/bin/endoreg-service-user-deploy-maintenance-secretfile";
      };
    };

    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
    };
  };
}
