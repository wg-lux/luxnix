{pkgs, ...}: {
    cli.programs.git = {
      enable = true;
      userName = "maddonix";
      email = "tlux14@googlemail.com";
      allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
    };

  desktops = {
    plasma = {
      enable = true;
    };
  };

  services.luxnix = {
    # syncthing.enable = false;
  };

  # luxnix.django-demo-app = {
  #   enable = true;
  # };
Re-uses ssh host keys from the sshd to not break .ssh/known_hosts
Authorized ssh keys are read from /root/.ssh/authorized_keys, /root/.ssh/authorized_keys2 and /etc/ssh/authorized_keys.d/root
  networking.usePredictableInterfaceNames = false;
  systemd.network = {
    enable = true;
    networks."eth0".extraConfig = ''
      [Match]
      Name = eth0
      [Network]
      # Add your own assigned ipv6 subnet here here!
      Address = 2a01:4f8:a0:93ba::/64
      Gateway = fe80::1
      # optionally you can do the same for ipv4 and disable DHCP (networking.dhcpcd.enable = false;)
      # Address =  144.x.x.x/26
      # Gateway = 144.x.x.1
    '';
  };


  roles = {
    development.enable = true;
    social.enable = true;
    gpu.enable = true;
    video.enable = true;
  };

  home.stateVersion = "23.11";
}
