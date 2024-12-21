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
  };

  config = mkIf cfg.enable {
    programs.tmux.enable = true;

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
      # ${pkgs.direnv}/bin/direnv allow
      echo "lx-django-template copied to $targetDir and direnv allowed"

      echo "Running devenv up"
      ############# REMOVE AFTER PROTOTYPING #############
      cd "$HOME/dev/lx-django-template"
      ####################################################

      # Run devenv up in a new detached tmux session
      ${pkgs.tmux}/bin/tmux new-session -d -s django-demo-app "${pkgs.devenv}/bin/devenv up"
    '';

    # add zsh aliases to open the tmux session
    programs.zsh.shellAliases = {
      tm-django-demo-app = "tmux new-session -A -s django-demo-app";
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
