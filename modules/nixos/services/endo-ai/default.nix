{ config
, lib
, pkgs
, ...
}:
#CHANGEME
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.endoAi;
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;

  adminName = config.user.admin.name;
  scriptName = "runEndoAi";

  gitURL = "https://github.com/wg-lux/endo-ai";
  repoDirName = "endo-ai";


  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  repoDir = "${endoreg-service-user-home}/${repoDirName}";

  runEndoAiScript = pkgs.writeShellScriptBin "${scriptName}" ''
    if [ ! -d ${repoDir} ]; then
      git clone ${gitURL} ${repoDir}
    else
      cd ${repoDir}
      git pull
    fi
    cd ${repoDir}

    # we can also use specific branches: checkout and pull branch "v0.1.1"
    git checkout stable
    git pull
    exec devenv shell -- run-prod-server
  '';


in
{
  options.services.luxnix.endoAi = {
    enable = mkBoolOpt false "Enable EndoAI Service";
  };

  config = mkIf cfg.enable {

    systemd.services."endo-ai" = {
      description = "Clone or pull endoreg-ai and run prod server";
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        Type = "exec";
        User = endoreg-service-user-name;
        # WorkingDirectory = repoDir;
        Environment = "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:/run/current-system/sw/bin";
        ExecStart = "${runEndoAiScript}/bin/${scriptName}";
        # Restart = "always"; # optionally restart if crashes occur
        # RestartSec = 120; # optional wait time before restart
      };
    };
  };
}
