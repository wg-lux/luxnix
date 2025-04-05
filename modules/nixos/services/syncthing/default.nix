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
    
    # Get the home directory of the syncthing user
    syncthingHome = config.users.users.${cfg.user}.home;
    
    # Helper to resolve paths with proper home dir
    resolvePath = path:
        if hasPrefix "~/" path then
            "${syncthingHome}/${removePrefix "~/" path}"
        else
            path;
    
    # return list of all device ids
    getSyncthingIds = hostConfigs: 
        mapAttrs (hostName: hostConfig: hostConfig.syncthing-id) hostConfigs;

    # Define a function which expects a list of hostnames and 
    # returns a list of their syncthing-ids
    getSyncthingIdsOfHosts = hostNames: 
        map (hostName: hostConfigs.${hostName}.syncthing-id) hostNames;

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

    # Map from device names to their IDs for easier reference
    deviceIds = mapAttrs (_: device: device.id) syncthingDevices;
    
    # Reverse mapping from IDs to device names
    idToName = mapAttrs' (name: device: nameValuePair device.id name) syncthingDevices;
    
    # More robust device resolution with logging for unrecognized devices
    resolveDeviceName = deviceName:
        if hasAttr deviceName deviceIds then
            # It's a known device name
            { resolved = true; name = deviceName; }
        else if hasAttr deviceName idToName then
            # It's a known device ID, convert to name
            { resolved = true; name = idToName.${deviceName}; }
        else
            # Unrecognized device - log and return as-is
            let
                _ = builtins.trace "Warning: Unrecognized Syncthing device '${deviceName}'. " null;
            in
            { resolved = false; name = deviceName; };

    # Generate folder configuration with improved validation and stringification
    generateFolders = folders:
        mapAttrs (folderName: folderOpts: {
            enable = folderOpts.enable;
            path = resolvePath folderOpts.path;
            label = if folderOpts.label != null 
                    then folderOpts.label 
                    else folderOpts.id;
            id = folderOpts.id;
            
            # More robust device resolution
            devices = map (deviceName: 
                let result = resolveDeviceName deviceName;
                in result.name
            ) folderOpts.devices;
            
            # Pass through other folder options
            type = folderOpts.type;
            fsWatcherEnabled = folderOpts.fsWatcherEnabled or true;
            # Convert numeric parameters to strings for the Syncthing API
            versioning = 
                if folderOpts.versioning.enable then {
                    type = folderOpts.versioning.type;
                    params = mapAttrs (name: value: 
                        if isInt value || isFloat value then toString value else value
                    ) folderOpts.versioning.params;
                } else null;
        }) folders;

    # Function to redact sensitive info for logging
    redactFolderConfig = config:
        mapAttrs (name: folder: {
            id = folder.id;
            label = folder.label;
            type = folder.type;
            enabled = folder.enable or true;
            # Mask actual path to avoid leaking sensitive locations
            path = if cfg.debugMode 
                   then folder.path 
                   else "<redacted>";
            deviceCount = length (folder.devices or []);
        }) config;

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
        extraFlags = mkOpt (types.listOf types.str) [] "Extra flags for syncthing";
        
        # Security and privacy settings
        folderPermissions = mkOption {
            type = types.str;
            default = "0750"; # More restrictive default for shared folders
            description = "Permissions for syncthing folders (in octal format)";
        };
        
        debugMode = mkOption {
            type = types.bool;
            default = false;
            description = "Enable verbose debug logging (may include sensitive information)";
        };
        
        apiWaitTimeoutSecs = mkOption {
            type = types.int;
            default = 60;
            description = "Maximum time to wait for the Syncthing API to be available (in seconds)";
        };

        # New folder options
        folders = mkOption {
            type = types.attrsOf (types.submodule {
                options = {
                    enable = mkOption {
                        type = types.bool;
                        default = true;
                        description = "Whether to enable this folder";
                    };
                    path = mkOption {
                        type = types.str;
                        description = "Path to the folder on disk";
                    };
                    label = mkOption {
                        type = types.nullOr types.str;  # Changed from types.str to types.nullOr types.str
                        default = null;
                        description = "Display name for the folder";
                    };
                    id = mkOption {
                        type = types.str;
                        description = "Unique ID for the folder - must be the same across all devices";
                    };
                    devices = mkOption {
                        type = types.listOf types.str;
                        default = [];
                        description = "Devices to share this folder with (names or IDs)";
                    };
                    fsWatcherEnabled = mkOption {
                        type = types.bool;
                        default = true;
                        description = "Watch for changes in real time (inotify)";
                    };
                    type = mkOption {
                        type = types.enum ["sendreceive" "sendonly" "receiveonly" "receiveencrypted"];
                        default = "sendreceive";
                        description = "Folder sharing type";
                    };
                    versioning = {
                        enable = mkOption {
                            type = types.bool;
                            default = true;
                            description = "Whether to enable versioning for this folder";
                        };
                        type = mkOption {
                            type = types.enum ["simple" "staggered" "trashcan" "external"];
                            default = "simple";
                            description = "Versioning strategy type";
                        };
                        params = mkOption {
                            type = types.attrsOf types.anything;
                            default = {
                                interval = 1;
                                maxAge = 30;
                            };
                            description = "Parameters for the versioning strategy";
                        };
                    };
                };
            });
            default = {
                "base-share" = {
                    path = "/var/lib/syncthing/base-share";
                    id = "base-share";
                    label = "base-share";  # Added explicit label to match id
                    # Default to sharing with all devices
                    devices = attrNames hostsWithSyncthing;
                    type = "sendreceive";
                    versioning = {
                        enable = true;
                        type = "simple";
                        params = {
                            interval = 1;
                            maxAge = 30;
                        };
                    };
                };
            };
            description = "Folders to be shared by Syncthing";
        };
    };

    config = mkIf cfg.enable {
        # Create necessary directories with configurable permissions
        systemd.tmpfiles.rules = [
            # System directories - moderate permissions
            "d /var/lib/syncthing 0755 ${cfg.user} ${syncthingGroup} -"
            "d ${cfg.defaultFolderPath} 0755 ${cfg.user} ${syncthingGroup} -"
        ] ++ (mapAttrsToList (name: folder: 
            # Shared folders - use configurable permissions
            "d ${resolvePath folder.path} ${cfg.folderPermissions} ${cfg.user} ${syncthingGroup} -"
        ) cfg.folders);
        
        # Ensure the base folder exists and is writable with proper permissions
        system.activationScripts.createSyncthingFolders = {
            deps = [];
            text = ''
                mkdir -p /var/lib/syncthing/base-share
                chown -R ${cfg.user}:${syncthingGroup} /var/lib/syncthing
                chmod -R ${cfg.folderPermissions} /var/lib/syncthing
            '';
        };

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

                # Print more detailed debug information with privacy controls
                devices = let 
                    devs = if cfg.debugMode then
                        builtins.trace "Syncthing devices: ${builtins.toJSON syncthingDevices}" finalDevices
                    else
                        builtins.trace "Configured ${toString (length (attrNames syncthingDevices))} Syncthing devices" 
                        finalDevices;
                in devs;

                folders = let
                    generatedFolders = generateFolders cfg.folders;
                    
                    # Print folder config with sensitive data redacted unless in debug mode
                    redactedConfig = redactFolderConfig generatedFolders;
                    
                    finalFolders = builtins.trace 
                        "Syncthing folders: ${builtins.toJSON redactedConfig}"
                        generatedFolders;
                in finalFolders;
            };
            
            # Add flags to reset database to ensure clean state
            extraFlags = cfg.extraFlags ++ ["--reset-deltas"];
        };
        
        # Wait for Syncthing API with configurable timeout
        systemd.services.syncthing-wait-api = {
            description = "Wait for Syncthing API to be available";
            after = [ "syncthing.service" ];
            bindsTo = [ "syncthing.service" ];
            before = [ "syncthing-init.service" "syncthing-folder-check.service" ];
            wantedBy = [ "multi-user.target" ];
            serviceConfig = {
                Type = "oneshot";
                User = cfg.user;
                RemainAfterExit = true;
                ExecStart = pkgs.writeShellScript "wait-syncthing-api" ''
                    #!/bin/bash
                    set -euo pipefail
                    
                    echo "Waiting for Syncthing to start up (timeout: ${toString cfg.apiWaitTimeoutSecs}s)..."
                    # Wait for configurable timeout
                    for i in $(seq 1 ${toString cfg.apiWaitTimeoutSecs}); do
                        if [ -f ${cfg.defaultFolderPath}/.config/syncthing/config.xml ]; then
                            echo "Configuration file found, checking API..."
                            # Try to get API key
                            if API_KEY=$(grep -o 'apikey>[^<]*' ${cfg.defaultFolderPath}/.config/syncthing/config.xml | sed 's/apikey>//'); then
                                echo "API key found, testing API..."
                                # Test if API is responsive
                                if ${pkgs.curl}/bin/curl -s -f -H "X-API-Key: $API_KEY" \
                                    "http://127.0.0.1:${toString cfg.port}/rest/system/ping" > /dev/null; then
                                    echo "Syncthing API is ready!"
                                    exit 0
                                fi
                            fi
                        fi
                        sleep 1
                    done
                    
                    echo "Timed out waiting for Syncthing API to be available"
                    exit 1
                '';
            };
        };
        
        # Update the init service to depend on the wait-api service
        systemd.services.syncthing-init = {
            after = [ "syncthing.service" "syncthing-wait-api.service" ];
            bindsTo = [ "syncthing.service" ];
            requires = [ "syncthing-wait-api.service" ];
            wantedBy = [ "multi-user.target" ];
        };
        
        # Enhanced folder-check service with more detailed validation
        systemd.services.syncthing-folder-check = {
            description = "Check Syncthing Folder Status";
            after = [ "syncthing.service" "syncthing-init.service" "syncthing-wait-api.service" ];
            requires = [ "syncthing-wait-api.service" ];
            bindsTo = [ "syncthing.service" ];
            wantedBy = [ "multi-user.target" ];
            serviceConfig = {
                Type = "oneshot";
                User = cfg.user;
                ExecStart = pkgs.writeShellScript "check-syncthing-folders" ''
                    #!/usr/bin/env zsh
                    set -euo pipefail
                    
                    echo "Getting API key from config.xml..."
                    CONFIG_FILE="${cfg.defaultFolderPath}/.config/syncthing/config.xml"
                    if [ ! -f "$CONFIG_FILE" ]; then
                        echo "Config file not found at $CONFIG_FILE"
                        exit 1
                    fi
                    
                    API_KEY=$(grep -o 'apikey>[^<]*' "$CONFIG_FILE" | sed 's/apikey>//')
                    if [ -z "$API_KEY" ]; then
                        echo "Could not find API key in config file"
                        exit 1
                    fi
                    
                    echo "Checking folders configuration..."
                    FOLDERS_JSON=$(${pkgs.curl}/bin/curl -s -f -H "X-API-Key: $API_KEY" \
                        "http://127.0.0.1:${toString cfg.port}/rest/config/folders")
                    
                    if [ $? -ne 0 ] || [ -z "$FOLDERS_JSON" ]; then
                        echo "Failed to get folders from API"
                        exit 1
                    fi
                    
                    echo "Current folders configuration:"
                    echo "$FOLDERS_JSON" | ${pkgs.jq}/bin/jq -C '. | map({id: .id, path: .path, devices: (.devices | length)})'
                    
                    FOLDER_COUNT=$(echo "$FOLDERS_JSON" | ${pkgs.jq}/bin/jq 'length')
                    echo "Configured folder count: $FOLDER_COUNT"
                    
                    # Enhanced folder validation
                    if [ "$FOLDER_COUNT" -eq 0 ]; then
                        echo "WARNING: No folders are configured in Syncthing!"
                    else
                        # Check if folders have devices
                        NO_DEVICE_FOLDERS=$(echo "$FOLDERS_JSON" | ${pkgs.jq}/bin/jq 'map(select(.devices | length == 0)) | length')
                        if [ "$NO_DEVICE_FOLDERS" -gt 0 ]; then
                            echo "WARNING: Found $NO_DEVICE_FOLDERS folders with no devices! These won't sync."
                        fi
                        
                        # Check folder states
                        echo "Checking folder states..."
                        FOLDER_IDS=$(echo "$FOLDERS_JSON" | ${pkgs.jq}/bin/jq -r '.[].id')
                        for id in $FOLDER_IDS; do
                            STATUS=$(${pkgs.curl}/bin/curl -s -f -H "X-API-Key: $API_KEY" \
                                "http://127.0.0.1:${toString cfg.port}/rest/db/status?folder=$id")
                            STATE=$(echo "$STATUS" | ${pkgs.jq}/bin/jq -r '.state')
                            echo "Folder $id: $STATE"
                        done
                    fi
                '';
            };
        };
    };
}
