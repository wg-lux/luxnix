{ config, lib, pkgs, ... }:

with lib; 
with lib.luxnix; let 
  repoInfo = builtins.fromJSON (builtins.readFile ./repo_info.json);

  lxDjangoRepo = pkgs.fetchFromGitHub {
    owner = "wg-lux";
    repo = "lx-django-template";
    rev = repoInfo.rev;
    sha256 = repoInfo.sha256;
  };

  cfg = config.luxnix.django-demo-app;

in {
  options.luxnix.django-demo-app = with types; {
    enable = mkBoolOpt false "Enable Django Demo App";
    bind = mkOption {
      type = types.str;
      default = "127.0.0.1";
    };

    port = mkOption {
      type = types.int;
      default = 9300;
    };

    testPort = mkOption {
      type = types.int;
      default = 8300;
    };

    appName = mkOption {
      type = types.str;
      default = "lx_django_template";
    };

    testDbHost = mkOption {
      type = types.str;
      default = "localhost";
    };

    testDbPort = mkOption {
      type = types.int;
      default = 5432;
    };

    testDbName = mkOption {
      type = types.str;
      default = "test_${cfg.appName}";
    };

    testDbUser = mkOption {
      type = types.str;
      default = "test_user_${cfg.appName}";
    };

    dbHost = mkOption {
      type = types.str;
      default = "localhost";
    };

    dbPort = mkOption {
      type = types.int;
      default = 5432;
    };
    
    dbName = mkOption {
      type = types.str;
      default = "${cfg.appName}";
    };

    dbUser = mkOption {
      type = types.str;
      default = "user_${cfg.appName}";
    };

    allowedHosts = mkOption {
      type = types.str;
      default = "localhost";
    };

    configTemplateFilename = mkOption {
      type = types.str;
      default = "nix-provisioned-settings.json";
    };

    configTemplate = mkOption {
      type = types.str;
      default = ''
        {
          "APP_NAME": "${cfg.appName}",
          "BIND": "${cfg.bind}",
          "PORT": "${toString cfg.port}",
          "ALLOWED_HOSTS": "${cfg.allowedHosts},${cfg.bind}",
          "DB_NAME": "${cfg.dbName}",
          "DB_HOST": "${cfg.dbHost}",
          "DB_PORT": "${toString cfg.dbPort}",
          "DB_USER": "${cfg.dbUser}",
          "TEST_DB_NAME": "${cfg.testDbName}",
          "TEST_DB_HOST": "${cfg.testDbHost}",
          "TEST_DB_PORT": "${toString cfg.testDbPort}",
          "TEST_DB_USER": "${cfg.testDbUser}",
          "DEBUG": "True",
          "DJANGO_SETTINGS_MODULE": "${cfg.appName}.settings",
        }
      '';
    };

  };

  config = mkIf cfg.enable {
    programs.tmux.enable = true;

    # write create ./config/lx-demo-app.json
    home.file.".config/${cfg.configTemplateFilename}" = {
      text = cfg.configTemplate;
    };

    # to check on created session:
    # tmux new-session -A -s django-demo-app

    # On activation, copy the repository to a writable directory
    home.activation.runDjangoDemoApp = lib.mkAfter ''
      targetDir="$HOME/lx-django-template"
      # create target dir if not exists
      mkdir -p "$targetDir"

      echo "Copying lx-django-template to $targetDir"
      # rm -rf "$targetDir"
      # mkdir -p "$targetDir"
      cp -rT ${lxDjangoRepo} "$targetDir"
      chmod -R u+rw,g+rw,o+r "$targetDir"

     
      cd "$targetDir"
      cp $HOME/.config/${cfg.configTemplateFilename} ./"${cfg.configTemplateFilename}"

      # ${pkgs.direnv}/bin/direnv allow
      echo "lx-django-template copied to $targetDir and direnv allowed"

      echo "Running devenv up"
      ############# REMOVE AFTER PROTOTYPING #############
      cd "$HOME/dev/lx-django-template" 
      cp $HOME/.config/${cfg.configTemplateFilename} ./"${cfg.configTemplateFilename}"

      ####################################################

      echo "Run 'django-demo-term' to open the tmux session"

      # Run devenv up in a new detached tmux session
      ${pkgs.tmux}/bin/tmux new-session -d -s django-demo-app "${pkgs.devenv}/bin/devenv up"
    '';

    # add zsh aliases to open the tmux session
    programs.zsh.shellAliases = {
      django-demo-term = "tmux new-session -A -s django-demo-app";
    };
  };
}


# let
#   # Fetch the lx-django-template repository at a known commit

# in {
#   home.username = "yourUser";

#   # Ensure devenv and any other required packages (like git) are available
#   home.packages = with pkgs; [
#     devenv
#     git
#   ];

#   # Place the repository into the home directory.
#   # This uses the 'recursive = true' option so that the entire directory is linked/copied.
#   home.file."lx-django-template" = {
#     source = lxDjangoRepo;
#     recursive = true;
#   };

#   # Define a systemd user service that starts the Django app via `devenv up`.
#   # This service:
#   # - Changes directory into the cloned repo
#   # - Runs `devenv up` which should start the Django development server as defined by the repo’s configuration
#   # - Restarts on failure to ensure it remains up
#   systemd.user.services."django-webapp" = {
#     description = "Django Web Application Service";

#     # The service should start when the default user target is reached.
#     wantedBy = [ "default.target" ];

#     # Set up environment and command for running the service
#     serviceConfig = {
#       WorkingDirectory = "${config.home.homeDirectory}/lx-django-template";
#       ExecStart = "${pkgs.devenv}/bin/devenv up";
#       Restart = "on-failure";
#     };
#   };
# }
