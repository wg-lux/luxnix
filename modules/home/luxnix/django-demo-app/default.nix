{ config, pkgs, ... }:

let
  # Fetch the lx-django-template repository at a known commit
  lxDjangoRepo = pkgs.fetchFromGitHub {
    # get latest: nix-prefetch-git https://github.com/wg-lux/lx-django-template
    owner = "wg-lux";
    repo = "lx-django-template";
    # Replace with a stable revision of the repo
    rev = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    # Replace with the correct sha256 from nix-prefetch-git
    sha256 = "sha256-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa=";
  };
in {
  home.username = "yourUser";

  # Ensure devenv and any other required packages (like git) are available
  home.packages = with pkgs; [
    devenv
    git
  ];

  # Place the repository into the home directory.
  # This uses the 'recursive = true' option so that the entire directory is linked/copied.
  home.file."lx-django-template" = {
    source = lxDjangoRepo;
    recursive = true;
  };

  # Define a systemd user service that starts the Django app via `devenv up`.
  # This service:
  # - Changes directory into the cloned repo
  # - Runs `devenv up` which should start the Django development server as defined by the repo’s configuration
  # - Restarts on failure to ensure it remains up
  systemd.user.services."django-webapp" = {
    description = "Django Web Application Service";

    # The service should start when the default user target is reached.
    wantedBy = [ "default.target" ];

    # Set up environment and command for running the service
    serviceConfig = {
      WorkingDirectory = "${config.home.homeDirectory}/lx-django-template";
      ExecStart = "${pkgs.devenv}/bin/devenv up";
      Restart = "on-failure";
    };
  };
}
