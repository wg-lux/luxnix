{ config
, lib
, pkgs
, ...
}:
#CHANGEME
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.endoregDbApiLocal;
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;

  adminName = config.user.admin.name;
  scriptName = "runLocalEndoRegDbApi";

  gitURL = "https://github.com/wg-lux/endoreg-db-api";
  repoDirName = "endoreg-db-api";


  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";

  runLocalEndoRegDbApiScript = pkgs.writeShellScriptBin "${scriptName}" ''
    if [ ! -d ${repoDir} ]; then
      git clone ${gitURL} ${repoDir}
    else
      cd ${repoDir}
      git pull
    fi
    cd ${repoDir}

    # we can also use specific branches: checkout and pull branch "v0.1.1"
    # git checkout v0.1.1
    git pull
    exec devenv shell -- run-prod-server
  '';


in
{
  options.services.luxnix.endoregDbApiLocal = {
    enable = mkBoolOpt false "Enable EndoRegDbApi Service";


  };

  config = mkIf cfg.enable {

    # service to deploy secretfile
    # src /etc/secrets/vault/SCRT_local_password_maintenance_password
    # dst "${endoreg-service-user-home}/SCRT_local_password_maintenance_password"



    systemd.services."endoreg-db-api-boot" = {
      description = "Clone or pull endoreg-db-api and run devenv up";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        # WorkingDirectory = repoDir;
        Environment = "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:/run/current-system/sw/bin";
        ExecStart = "${runLocalEndoRegDbApiScript}/bin/${scriptName}";
        # Restart = "always"; # optionally restart if crashes occur
        # RestartSec = 120; # optional wait time before restart
      };
    };
  };
}
