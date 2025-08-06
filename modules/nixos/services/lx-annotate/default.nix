{ config, lib, pkgs, ... }:
with lib;
let
  cfg = config.services.luxnix.lxAnnotate;
  adminName = config.user.admin.name;
  scriptName = "runLxAnnotate";
  gitURL = cfg.repository.url or "https://github.com/wg-lux/lx-annotate.git";
  repoDirName = "lx-annotate";
  branchName = cfg.repository.branch or "main";
  serviceUserName = config.user.lx-annotate-service-user.name or "lx-annotate-service-user";
  serviceUser = config.users.users.${serviceUserName};
  serviceUserHome = serviceUser.home;
  repoDir = "${serviceUserHome}/${repoDirName}";
  passwordFile = cfg.database.passwordFile or "/etc/secrets/vault/SCRT_local_password_lx_annotate";
  dbName = cfg.database.name or "lxAnnotateDb";
  dbUser = cfg.database.user or "lxAnnotateUser";
  dbHost = cfg.database.host or "localhost";
  dbPort = toString (cfg.database.port or 5432);

  # Example: generate a config file for the app (adapt as needed for your app)
  appConfigFile = pkgs.writeText "lx-annotate-db.conf" ''
    DB_NAME=${dbName}
    DB_USER=${dbUser}
    DB_PASSWORD=$(cat ${passwordFile})
    DB_HOST=${dbHost}
    DB_PORT=${dbPort}
  '';

  runLxAnnotateScript = pkgs.writeShellScriptBin scriptName ''
    set -euo pipefail
    echo "Starting lx-annotate service..."
    echo "Repository: ${gitURL}"
    echo "Branch: ${branchName}"
    echo "Target Directory: ${repoDir}"
    if [ ! -d ${repoDir} ]; then
      echo "Cloning repository..."
      git clone ${gitURL} ${repoDir}
      cd ${repoDir}
    else
      cd ${repoDir}
      echo "Updating repository..."
      git fetch origin || { echo "ERROR: Failed to fetch from origin"; exit 1; }
    fi
    echo "Checking out branch: ${branchName}"
    if git show-ref --verify --quiet refs/heads/${branchName}; then
      git checkout ${branchName} || { echo "ERROR: Failed to checkout local branch ${branchName}"; exit 1; }
    elif git show-ref --verify --quiet refs/remotes/origin/${branchName}; then
      git checkout -b ${branchName} origin/${branchName} || { echo "ERROR: Failed to create tracking branch for ${branchName}"; exit 1; }
    else
      echo "ERROR: Branch ${branchName} does not exist locally or on remote"
      git branch -r || echo "Could not list remote branches"
      exit 1
    fi
    echo "Copying DB config..."
    mkdir -p ${repoDir}/conf
    cp ${appConfigFile} ${repoDir}/conf/db.conf
    echo "DB config copied to ${repoDir}/conf/db.conf"
    echo "Starting application..."
    exec devenv shell -- run-prod-server
  '';
in
{
  options.services.luxnix.lxAnnotate = {
   #enable = mkBoolOpt false "Enable lx-annotate Service";
    enable = mkEnableOption "Enable lx-annotate Service";
    database = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          host = mkOption { type = types.str; default = "localhost"; };
          port = mkOption { type = types.port; default = 5432; };
          name = mkOption { type = types.str; default = "lxAnnotateDb"; };
          user = mkOption { type = types.str; default = "lxAnnotateUser"; };
          passwordFile = mkOption { type = types.path; default = "/etc/secrets/vault/SCRT_local_password_lx_annotate"; };
        };
      });
      default = null;
      description = "Database configuration options";
    };
    repository = mkOption {
      type = types.nullOr (types.submodule {
        options = {
          url = mkOption { type = types.str; default = "https://github.com/wg-lux/lx-annotate.git"; };
          branch = mkOption { type = types.str; default = "main"; };
          updateOnBoot = mkOption { type = types.bool; default = true; };
        };
      });
      default = null;
      description = "Repository configuration options";
    };
  };

  config = mkIf cfg.enable {
    systemd.tmpfiles.rules = [
      "d ${serviceUserHome} 0755 ${serviceUserName} ${serviceUserName} - -"
      "d ${serviceUserHome}/config 0755 ${serviceUserName} ${serviceUserName} - -"
    ];
    systemd.services."lx-annotate" = {
      description = "Clone or pull lx-annotate and run prod server";
      wantedBy = [ "multi-user.target" ];
      after = [ "postgres-lx-annotate-setup.service" "systemd-tmpfiles-setup.service" ];
      requires = [ "postgres-lx-annotate-setup.service" "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "exec";
        User = serviceUserName;
        Environment = "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:/run/current-system/sw/bin";
        ExecStart = "${runLxAnnotateScript}/bin/${scriptName}";
        Restart = "on-failure";
        RestartSec = "10s";
        MemoryMax = "2G";
        CPUQuota = "200%";
      };
    };
  };
}
