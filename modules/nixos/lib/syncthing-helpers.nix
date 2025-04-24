{ lib, hostConfigs, ownNetworkCluster, hostname, cfg }:
with lib; rec {

  # Resolve "~/" paths relative to syncthing home
  resolvePath = path:
    if hasPrefix "~/" path
    then "${cfg.defaultFolderPath}/${removePrefix "~/" path}"
    else path;

  # Get prioritized Syncthing addresses based on clusters
  getSyncthingAddresses = hostName: let
    host = hostConfigs.${hostName} or {};
    targetCluster = host.network-cluster or null;
    sameCluster = ownNetworkCluster != null && targetCluster != null && ownNetworkCluster == targetCluster;
    ips = filter (ip: ip != null && ip != "")
      (if sameCluster then [host.ip-local host.ip-vpn] else [host.ip-vpn host.ip-local]);
    addresses = map (ip: "tcp://${ip}:${toString cfg.portTCP}") ips;
  in if hostName == hostname
     then ["tcp://127.0.0.1:${toString cfg.portTCP}"] ++ addresses
     else addresses;

  # Generate devices configuration for syncthing
  mkDevices = hostsWithSyncthing:
    mapAttrs (hostName: hostConfig: {
      name = hostName;
      id = hostConfig.syncthing-id;
      addresses = getSyncthingAddresses hostName;
      introducer = hostName == cfg.introducerHost && hostname != cfg.introducerHost;
      autoAcceptFolders = true;
    }) hostsWithSyncthing;

  # Safely generate syncthing folder configurations
  generateFolders = folders:
    mapAttrs (folderName: folderOpts: {
      enable = folderOpts.enable;
      path = resolvePath folderOpts.path;
      label = folderOpts.label or folderOpts.id;
      id = folderOpts.id;
      devices = folderOpts.devices;
      type = folderOpts.type;
      fsWatcherEnabled = folderOpts.fsWatcherEnabled or true;
      versioning =
        if folderOpts.versioning.enable then {
          type = folderOpts.versioning.type;
          params = mapAttrs (n: v: if isInt v then toString v else v) folderOpts.versioning.params;
        } else null;
    }) folders;

}
