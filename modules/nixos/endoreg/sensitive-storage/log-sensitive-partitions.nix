{ config, lib, pkgs, partitionConfiguration, ... }:

let
  hostname = config.networking.hostName;

  # Partition-specific configuration
  conf = partitionConfiguration;
  label = partitionConfiguration.label;
  luksUuid = partitionConfiguration.luks-uuid;
  uuid = partitionConfiguration.uuid;

  # Mountpoint and service configuration
  mountpoint = conf.mountPoint;
  scriptName = conf.logScriptName;
  serviceName = conf.logServiceName;
  timerName = conf.logServiceName;
  timerOnCalendar = conf.logTimerOnCalendar;

  # Keyfile path for encryption
  keyFile = conf.keyFile;

  # Logging configuration
  user = conf.user;
  group = conf.group;
  logDir = conf.logDir;

  # Create a state-checking script
  scriptPath = pkgs.writeShellScriptBin "${scriptName}" ''
    #!/bin/sh

    # Set timestamp
    timestamp=$(date +%Y-%m-%d_%H-%M-%S)
    outputFile="${logDir}/${hostname}-$timestamp-sensitive-${label}.json"

    # Initialize the default states
    keyfileExists="false"
    partitionAvailable="false"
    partitionMounted="false"
    partitionDecrypted="false"
    partitionSize="unknown"
    partitionUsed="unknown"

    # Check if keyfile exists
    if [ -f "${keyFile}" ]; then
      keyfileExists="true"
    fi

    # Check if the partition is available (exists in the system)
    if lsblk -f | grep -q "${uuid}"; then
      partitionAvailable="true"
    fi

    # Check if the partition is mounted
    if mount | grep -q "${mountpoint}"; then
      partitionMounted="true"
    fi

    # Check if the partition is decrypted
    if cryptsetup status ${luksUuid} 2>/dev/null | grep -q "is active"; then
      partitionDecrypted="true"
    fi

    # Get partition size and usage if the partition is available
    if [ "$partitionAvailable" = "true" ]; then
      partitionSize=$(lsblk -bno SIZE /dev/disk/by-uuid/${uuid} 2>/dev/null || echo "unknown")
      partitionUsed=$(df -B1 --output=used /dev/disk/by-uuid/${uuid} 2>/dev/null | tail -n1 || echo "unknown")
    fi

    # Create JSON file with the current state
    cat > $outputFile <<EOF
    {
      "hostname": "${hostname}",
      "timestamp": "$timestamp",
      "label": "${label}",
      "luks-uuid": "${luksUuid}",
      "uuid": "${uuid}",
      "mountpoint": "${mountpoint}",
      "keyfile-target": "${keyFile}",
      "keyfile-exists": $keyfileExists,
      "keyfile-owner": "$(stat -c '%U' ${keyFile} 2>/dev/null || echo "unknown")",
      "keyfile-group": "$(stat -c '%G' ${keyFile} 2>/dev/null || echo "unknown")",
      "keyfile-permissions": "$(stat -c '%A' ${keyFile} 2>/dev/null || echo "unknown")",
      "partition-available": $partitionAvailable,
      "partition-mounted": $partitionMounted,
      "partition-decrypted": $partitionDecrypted,
      "partition-size": "$partitionSize",
      "partition-used": "$partitionUsed"
    }
    EOF
  '';
in
{
  # Include the script in system packages
  environment.systemPackages = with pkgs; [
    scriptPath
  ];

  ########## SYSTEMD SERVICE ##########
  systemd.services."${serviceName}" = {
    description = "Mount and log ${label} HDD Service";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${scriptPath}/bin/${scriptName}";
      User = "root";
      Group = "root";
    };
    path = [ pkgs.sudo pkgs.cryptsetup pkgs.util-linux pkgs.coreutils pkgs.gnugrep pkgs.jq ];
  };

  ########## SYSTEMD TIMER ##########
  systemd.timers."${timerName}" = {
    wantedBy = [ "timers.target" ];
    description = "Timer for ${serviceName} service";
    timerConfig = {
      OnCalendar = timerOnCalendar; # Runs based on provided calendar, e.g., hourly
      Persistent = true; # Ensures it runs even if the system was off at the scheduled time
    };
    unitConfig = {};
  };

  ########## POLKIT RULES ##########
  security.polkit.extraConfig = ''
    polkit.addRule(function(action, subject) {
      if (action.id == "org.freedesktop.systemd1.manage-units" &&
          subject.isInGroup("${group}") &&
          action.lookup("unit") == "${serviceName}.service" &&
          (action.lookup("verb") == "start" || action.lookup("verb") == "stop")) {
        return polkit.Result.YES;
      }
    });
  '';
}
