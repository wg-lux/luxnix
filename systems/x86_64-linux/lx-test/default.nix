{ config, lib, pkgs, ... }:

{
  # This host is intentionally hardware-neutral so it can be installed as a
  # VM or on a small dedicated server. Add a host-specific disko definition
  # when the target machine is chosen.
  networking.hostName = "lx-test";

  # A conventional VM-friendly root filesystem placeholder. Replace this
  # with the target's disko layout before a bare-metal installation.
  fileSystems."/" = {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
  };
  boot.loader.systemd-boot.enable = true;

  user = {
    admin.name = "admin";
    ansible.enable = true;
    settings.mutable = false;
  };

  roles = {
    aglnet.client.enable = lib.mkForce false;
    common.enable = true;
    custom-packages.enable = true;
  };

  services = {
    nginx.enable = true;

    luxnix.lxAnnotateLocal = {
      enable = true;
      # Use the flake-provided package by default; this makes the host a
      # reproducible integration target instead of a source checkout.
      runtime = {
        mode = "repo";
        deploymentRole = "standalone";
        trainingWorker.mode = "manual";
        inferenceWorker.mode = "manual";
        llmInferenceWorker.mode = "manual";
        ffmpegWorker.mode = "always";
      };
      django = {
        hostname = "lx-test.intern";
        baseUrl = "http://lx-test.intern";
        httpProtocol = "http";
        useHttps = false;
        djangoAllowedHosts = [ "lx-test" "lx-test.intern" "localhost" "127.0.0.1" ];
      };
    };
  };

  luxnix = {
    dns.enable = true;
    generic-settings = {
      enable = true;
      hostPlatform = "x86_64-linux";
      systemStateVersion = "23.11";
      language = "english";
    };
  };
}
