{ config, lib, pkgs, ... }:
with lib; 
with lib.luxnix; let
    cfg = config.services.luxnix.syncthing;

    gs = config.luxnix.generic-settings;
    hostConfigs = gs.network.hosts;
    etcHosts = config.networking.hosts;
    adminUser = config.user.admin.name;

    # Get current host's cluster
    hostname = config.networking.hostName;
    ownNetConfig = hostConfigs.${hostname} or {};
    ownNetworkCluster = ownNetConfig.network-cluster or null;

    syncthingGroup = config.users.users.${config.services.syncthing.user}.group;
    
    # Function to get valid IP addresses for a hostname with proper prioritization
    get_syncthing_addresses = hostName: 
        let
            # Get the target host configuration
            host = hostConfigs.${hostName} or {};
            targetCluster = host.network-cluster or null;
            
            # Determine if host is in the same cluster
            sameCluster = ownNetworkCluster != null && targetCluster != null && 
                         ownNetworkCluster == targetCluster;
            
            # Get available IPs
            localIp = host.ip-local or null;
            vpnIp = host.ip-vpn or null;
            
            # Create prioritized list based on cluster relationship
            prioritizedIps = 
                if sameCluster && localIp != null then
                    # Same cluster: local IP first, then VPN IP as fallback
                    filter (ip: ip != null && ip != "") [ localIp vpnIp ]
                else
                    # Different cluster: VPN IP first, then local IP as fallback
                    filter (ip: ip != null && ip != "") [ vpnIp localIp ];
                    
            # Create addresses from IPs
            addresses = map (ip: "tcp://${ip}:${toString cfg.portTCP}") prioritizedIps;
            
            # Add localhost as highest priority if this is the current system
            finalAddresses = 
                if hostName == hostname then
                    ["tcp://127.0.0.1:${toString cfg.portTCP}"] ++ addresses
                else
                    addresses;
                    
            # debug = builtins.trace "Getting addresses for ${hostName} (same cluster: ${toString sameCluster}, self: ${toString (hostName == hostname)}): ${builtins.toJSON finalAddresses}" finalAddresses;
        in finalAddresses;

    # Filter hosts that have a syncthing-id
    hostsWithSyncthing = filterAttrs 
        (hostName: hostConfig: hostConfig.syncthing-id != null && hostConfig.syncthing-id != "") 
        hostConfigs;
    
    # Create devices attribute set with introducer flag set to true
    syncthingDevices = mapAttrs 
        (hostName: hostConfig: {
            name = hostName;
            id = hostConfig.syncthing-id;
            addresses = get_syncthing_addresses hostName;
            introducer = true;  # Add this line to auto-accept introduced devices
            autoAcceptFolders = true;  # Add this to auto-accept folders
        }) 
        hostsWithSyncthing;
    
    # Default device if empty
    finalDevices = if syncthingDevices == {} 
                  then { "dummy-device" = { name = "dummy-device"; id = "DUMMY"; addresses = []; }; }
                  else syncthingDevices;

in
{
    options.services.luxnix.syncthing = {
        enable = mkBoolOpt false "Enable syncthing";
        gui = mkBoolOpt false "Enable syncthing GUI";
        gui-public = mkBoolOpt false "Enable syncthing GUI";
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
        networking.firewall.allowedUDPPorts = [ cfg.localAnnouncePort ];
        services.syncthing = {
            enable = cfg.enable; 
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
                    address = cfg.gui-ip + ":" + toString cfg.port;
                };
                options = {
                    urAccepted = -1;
                    localAnnouncePort = cfg.localAnnouncePort;
                    localAnnounceEnabled = cfg.localAnnounceEnabled;
                    globalAnnounceEnabled = false;
                };

                # Print more detailed debug information
                devices = let 
                    devs = builtins.trace 
                        "Configured Syncthing devices: ${builtins.concatStringsSep ", " (attrNames syncthingDevices)}"
                        finalDevices;
                in devs;

                folders = {
                    "base-share" = {
                        enable = true;
                        path = "~/base-share";
                        label = "base-share";
                        id = "base-share";
                        # Map device names to strings (not objects)
                        devices = attrNames syncthingDevices;
                        type = "sendreceive";
                        versioning = {
                            type = "simple";
                            params = {
                                interval = 1;
                                maxAge = 30;
                            };
                        };
                    };
                };
            };
            # Using ["--reset-deltas"] can be helpful if you’re troubleshooting
            # issues with incremental sync. It forces Syncthing to rebuild its internal index of file blocks, 
            # sometimes resolving corruption or mismatch.
            extraFlags = [];
        };
    };
}
