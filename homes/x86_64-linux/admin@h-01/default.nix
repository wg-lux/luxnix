# /default.nix
_: {
  cli = {
    programs = {
      git = {
        allowedSigners = "SHA256:LNfWnvEthO0QL8DzUxtxHD4VnLxvCZWFmcDhZodk29o";
        enable = true;
        email = "tlux14@googlemail.com";
        userName = "maddonix";
      };
    };
  };
  desktops = {
    plasma = {
      enable = true;
    };
  };
  networking = {
    networking = {
      usePredictableInterfaceNames = false;
    };
    systemd = {
      network = {
        enable = true;
        networks = {
          "eth0" = {
            extraConfig = "[Match]
Name = eth0
[Network]
Address = 2a01:4f8:a0:93ba::/64
Gateway = fe80::1
# optionally you can do the same for ipv4 and disable DHCP (networking.dhcpcd.enable = false;)
# Address =  144.x.x.x/26
# Gateway = 144.x.x.1
";
          };
        };
      };
    };
  };
  luxnix = {
    generic-settings = {
      language = "english";
      hostPlatform = "x86_64-linux";
    };
  };
  roles = {
    development = {
      enable = true;
    };
    video = {
      enable = true;
    };
  };

  home.stateVersion = "23.11";
}
