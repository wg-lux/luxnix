{ config, lib, pkgs, ... }:
with lib; 
with lib.luxnix; let
    cfg = config.services.luxnix.syncthing;

    gs = config.luxnix.generic-settings;
    adminUser = config.user.admin.name;

    syncthingGroup = config.users.users.${config.services.syncthing.user}.group;

in
{
    options.services.luxnix.syncthing = {
        enable = mkBoolOpt false "Enable syncthing";
        gui = mkBoolOpt false "Enable syncthing GUI";
        gui_public = mkBoolOpt false "Enable syncthing GUI";
        relay = mkBoolOpt false "Enable syncthing relay";
        gui-ip = mkOption {
            type = types.str;
            default = "127.0.0.1";
            description = "IP address for the syncthing GUI";
        };
        user = mkOpt types.str "syncthing" "User to run syncthing as";
        port = mkOpt types.port 8384 "Port for the syncthing web interface";
        portTCP = mkOpt types.port 22000 "Port for the syncthing TCP connection";
        defaultFolderPath = mkOpt types.path "/var/lib/syncthing" "Default folder path for syncthing";
        adminConfigReadPermission = mkBoolOpt true "Grant admin read permission";
        localAnnounceEnabled = mkBoolOpt true "Enable Local Announcements";
        localAnnouncePort = mkOpt types.int 21027 "Local Announcement TDP";
    };

    config = mkIf cfg.enable {


        users.users.${adminUser}.extraGroups = [ syncthingGroup ];


        networking.firewall.allowedTCPPorts = [ cfg.portTCP ];
      networking.firewall.allowedUDPPorts = [ cfg.localAnnouncePort ]; # Disabled since we dont use
        services.syncthing = {
            enable = cfg.enable; 
            # enable = false; 
            user = cfg.user;
            relay.enable = cfg.relay;
            openDefaultPorts = false; # We open the ports manually
            overrideDevices = true; # We override manually configured devices
            overrideFolders = true; # We override manually configured folders
            dataDir = cfg.defaultFolderPath; # Defaults to "config.services.syncthing.dataDir";
            # configDir = ; # Defaults to "config.services.syncthing.dataDir" + "/.config/syncthing;
            # database_dir = ;# Defaults to "config.services.syncthing.configDir";


            settings = {
                gui = {
                    enabled = true;
                    # Only localhost for safety, or "0.0.0.0:8384" if you want LAN access
                    address = cfg.gui-ip + ":" + toString cfg.port;
                };
                options = {
                    urAccepted = -1; # no anonymous usage reporting
                    localAnnouncePort = cfg.localAnnouncePort; # local LAN broadcast port
                    localAnnounceEnabled = cfg.localAnnounceEnabled;  # enable local LAN broadcast
                    globalAnnounceEnabled = false; # disable use of public relay discovery
                };

                devices = {};

                
                #  https://docs.syncthing.net/users/config.html#config-option-folder.type
                folders = {};
            };
            # Using ["--reset-deltas"] can be helpful if you’re troubleshooting
            # issues with incremental sync. It forces Syncthing to rebuild its internal index of file blocks, 
            # sometimes resolving corruption or mismatch.
            extraFlags = [];
        };
    };
}
