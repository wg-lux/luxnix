{
  config,
  lib,
  ...
}:
with lib; let
  cfg = config.services.virtualisation.podman;
in {
  options.services.virtualisation.podman = {
    enable = mkEnableOption "Enable podman";
  };

  config = mkIf cfg.enable {
    virtualisation = {
      podman = {
        enable = true;
        dockerSocket.enable = true;
        dockerCompat = true;
        defaultNetwork.settings = {
          dns_enabled = true;
        };
      };
    };

    # Ensure docker socket has correct permissions
    # systemd.tmpfiles.rules = [
    #   "d /run/docker 0750 root docker -"
    #   "z /run/docker.sock 0660 root docker -"
    # ];
  };
}