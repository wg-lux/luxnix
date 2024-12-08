{
  config,
  lib,
  pkgs,
  ...
}:
#CHANGEME
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.nfs;
in {
  options.services.luxnix.nfs = {
    enable = mkBoolOpt false "Enable the (mount) nfs drive";
  };

  config = mkIf cfg.enable {
    sops.secrets.nfs_smb_secrets = {
      sopsFile = ../secrets.yaml;
    };

    environment.systemPackages = with pkgs; [
      cifs-utils
      nfs-utils
    ];

    fileSystems."/mnt/share" = {
      device = "//192.168.1.73/Data/homelab";
      fsType = "cifs";
      options = let
        # this line prevents hanging on network split
        automount_opts = "x-systemd.automount,x-systemd.idle-timeout=60,x-systemd.device-timeout=5s,x-systemd.mount-timeout=5s";
      in [
        "${automount_opts},credentials=${config.sops.secrets.nfs_smb_secrets.path}"
        "uid=root"
        "gid=media"
        "file_mode=0664"
        "dir_mode=0775"
      ];
    };
  };
}
