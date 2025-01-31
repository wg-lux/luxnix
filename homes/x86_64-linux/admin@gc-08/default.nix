{pkgs, ...}: {
    cli.programs.git = {
      enable = true;
      userName = "hamzaukw";
      email = "hamza.ukw@gmail.com";
      allowedSigners = "SHA256:h8mCzXwuV6bbZVgKiaaoL8sWjgzerZz1lsHonWBrkO0";
    };

  desktops = {
    plasma = {
      enable = true;
    };
  };

  services.luxnix = {
    # syncthing.enable = false;
  };

  services.ssh-agent.enable = true;


  # luxnix.django-demo-app = {
  #   enable = true;
  # };

  roles = {
    development.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
