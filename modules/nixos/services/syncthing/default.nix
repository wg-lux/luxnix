{ config, lib, pkgs, ... }:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.syncthing;
  gs = config.luxnix.generic-settings;
  hostConfigs = gs.network.hosts;
  hostname = config.networking.hostName;
  ownNetworkCluster = (hostConfigs.${hostname}.network-cluster or null);

  syncthingGroup = config.users.users.${cfg.user}.group;
  syncthingHome = cfg.defaultFolderPath;

  hostsWithSyncthing = filterAttrs (_: h: h.syncthing-id != null) hostConfigs;

  helpers = import ../../lib/syncthing-helpers.nix {
    inherit lib hostConfigs ownNetworkCluster hostname cfg;
  };

  devices = helpers.mkDevices hostsWithSyncthing;
  folders = helpers.generateFolders cfg.folders;

in {
  options.services.luxnix.syncthing = {
    enable = mkEnableOption "Enable syncthing";
    extraFlags = mkOpt (types.listOf types.str) [] "Extra flags for syncthing";
    user = mkOption {
      type = types.str;
      default = "syncthing";
    };
    gui-ip = mkOption {
      type = types.str;
      default = "127.0.0.1";
    };
    port = mkOption {
      type = types.port;
      default = 8384;
    };
    portTCP = mkOption {
      type = types.port;
      default = 22000;
    };
    defaultFolderPath = mkOption {
      type = types.str;
      default = "/var/lib/syncthing";
    };
    introducerHost = mkOption {
      type = types.str;
      default = "gc-06";
    };
    folders = mkOption {
      type = types.attrs;
      default = {
        "base-share" = {
          path = "~/base-share";
          id = "base-share";
          devices = attrNames hostsWithSyncthing;
          enable = true;
          type = "sendreceive";
          versioning = {
            enable = true;
            type = "simple";
            params = { interval = 1; maxAge = 30; };
          };
        };
      };
    };
    folderPermissions = mkOption {
      type = types.str;
      default = "0750";
    };
  };

  config = mkIf cfg.enable {
    users.users.${cfg.user} = {
      isSystemUser = true;
      home = syncthingHome;
      createHome = true;
      extraGroups = ["network"];
    };

    users.users.${config.user.admin.name}.extraGroups = [syncthingGroup];

    systemd.tmpfiles.rules = [
      "d ${syncthingHome} 0750 ${cfg.user} ${syncthingGroup} -"
    ] ++ (mapAttrsToList (_: folder:
      "d ${helpers.resolvePath folder.path} ${cfg.folderPermissions} ${cfg.user} ${syncthingGroup} -"
    ) cfg.folders);

    networking.firewall.allowedTCPPorts = [cfg.portTCP];
    networking.firewall.allowedUDPPorts = [21027];

    services.syncthing = {
      inherit (cfg) enable user;
      dataDir = syncthingHome;
      # overrideDevices = true;
      # overrideFolders = true;
      settings = {
        gui = {
          enabled = true;
          address = "${cfg.gui-ip}:${toString cfg.port}";
        };
        options = {
          urAccepted = -1;
          localAnnouncePort = 21027;
          localAnnounceEnabled = true;
          globalAnnounceEnabled = false;
        };
        inherit devices folders;
      };
    };
  };
}
