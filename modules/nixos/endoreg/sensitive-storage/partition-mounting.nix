{ 
    config, 
    lib, 
    pkgs, 
    partitionConfiguration, 
    ... 
}:

let
    # add script
    conf = if config.endoreg.sensitive-storage.enable 
        then partitionConfiguration
        else  # dummy dictionary
            {
                label = "dummy";
                luks-uuid = "dummy";
                mountPoint = "dummy";
                filemodeSecret = "dummy";
                filemodeMountpoint = "dummy";
                mountScriptName = "dummy";
                umountScriptName = "dummy";
                mountServiceName = "dummy";
                umountServiceName = "dummy";
                keyFile = "dummy";
                user = "dummy";
                group = "dummy";
            };

    # endoreg-sensitive-hdd = network-config.hardware.${hostname}.endoreg-sensitive;

    label = partitionConfiguration.label;
    
    partition-luks-uuid = partitionConfiguration.luks-uuid;
    mountpoint = conf.mountPoint;
    filemode-secret = conf.filemodeSecret;
    filemode-mountpoint = conf.filemodeMountpoint;

    mount-script-name = conf.mountScriptName;
    umount-script-name = conf.umountScriptName;

    mount-service-name = conf.mountServiceName;
    umount-service-name = conf.umountServiceName;

    # Requires sops.sercrets. .... to be defined, happens after "in"
    key-file = conf.keyFile;

    user = conf.user;
    group = conf.group;
    
    ############ MOUNT SCRIPT ############
    mount-script-path = pkgs.writeShellScriptBin "${mount-script-name}" ''
        LOG_FILE="/var/log/mount-${label}.log"
        ERROR_LOG_FILE="/var/log/mount-${label}-error.log"

        # Function to log messages with timestamps
        log() {
            echo "[$(date)] $1" >> $LOG_FILE
        }

        # Function to log errors with timestamps
        log_error() {
            echo "[$(date)] ERROR: $1" >> $ERROR_LOG_FILE
        }

        # Start the script logging
        log "Starting to mount ${label} at ${mountpoint}."

        # Check if the mapper device already exists and remove it if necessary
        if [ -e /dev/mapper/${label} ]; then
            log "Device mapper ${label} already exists, attempting to remove it."
            if sudo cryptsetup close ${label}; then
                log "Successfully removed existing mapper device ${label}."
            else
                log_error "Failed to remove existing mapper device ${label}."
                exit 1
            fi
        fi

        # Decrypt the partition
        if sudo cryptsetup open UUID=${partition-luks-uuid} ${label} --key-file ${key-file}; then
            log "Successfully decrypted ${label} with UUID ${partition-luks-uuid}."

            # Create a mount point if it doesn't exist
            mkdir -p ${mountpoint} || { log_error "Failed to create mount point ${mountpoint}"; exit 1; }

            # Mount the file system
            if mount /dev/mapper/${label} ${mountpoint}; then
                log "Successfully mounted ${label} at ${mountpoint}."
            else
                log_error "Failed to mount ${label} at ${mountpoint}."
                sudo cryptsetup close ${label}  # Close the encrypted partition if mount fails
                exit 1
            fi

            # Set permissions and ownership
            sudo chown -R ${user}:${group} ${mountpoint} || log_error "Failed to set ownership of ${mountpoint} to ${user}:${group}"
            sudo chmod -R ${filemode-mountpoint} ${mountpoint} || log_error "Failed to set permissions of ${mountpoint} to ${filemode-mountpoint}"

        else
            log_error "Failed to decrypt ${label}."
            exit 1
        fi

        log "Mount operation completed."
    '';


    ############ UMOUNT SCRIPT ############
    umount-script-path = pkgs.writeShellScriptBin "${umount-script-name}" ''
      LOG_FILE="/var/log/mount-${label}.log"
      ERROR_LOG_FILE="/var/log/mount-${label}-error.log"
      
      log() {
          echo "[$(date)] $1" >> $LOG_FILE
      }

      log_error() {
          echo "[$(date)] ERROR: $1" >> $ERROR_LOG_FILE
      }

      log "Starting to unmount ${label} from ${mountpoint}."

      # Unmount the file system
      if umount ${mountpoint}; then
          log "Successfully unmounted ${label} from ${mountpoint}."
      else
          log_error "Failed to unmount ${label} from ${mountpoint}."
          exit 1
      fi

      # Close the encrypted partition
      if sudo cryptsetup close ${label}; then
          log "Successfully closed the encrypted partition ${label}."
      else
          log_error "Failed to close the encrypted partition ${label}."
          exit 1
      fi

      # Verify the unmount status
      if mount | grep ${mountpoint} > /dev/null; then
          log_error "Partition ${label} is still mounted at ${mountpoint}. Cleanup failed."
          exit 1
      fi

      # Remove the mount point directory if it's empty
      if rmdir ${mountpoint}; then
          log "Removed mount point directory ${mountpoint}."
      else
          log_error "Failed to remove mount point directory ${mountpoint}. Directory may not be empty."
      fi

      log "Unmount operation completed."
    '';


in
{

  #   ####### MOUNT SERVICE #########
    systemd.services."${mount-service-name}" = {
        description = "Mount ${label} HDD Service";
        serviceConfig = {
            Type = "oneshot";
            ExecStart = "${mount-script-path}/bin/${mount-script-name}";
            User="root";
            Group="root";
        };
        path = [ pkgs.sudo pkgs.cryptsetup pkgs.utillinux pkgs.coreutils ];
    };

  #   ####### UMOUNT SERVICE #########
    systemd.services."${umount-service-name}" = {
        description = "Umount ${label} HDD Service";
        serviceConfig = {
            Type = "oneshot";
            ExecStart = "${umount-script-path}/bin/${umount-script-name}";
            User="root";
            Group="root";
        };
        path = [ pkgs.sudo pkgs.cryptsetup pkgs.utillinux pkgs.coreutils ];
    };

    environment.systemPackages = with pkgs; [
      mount-script-path
      umount-script-path
  ];


  ####### POLKIT RULES #########
  security.polkit.extraConfig = ''
    ####### POLKIT RULES MOUNT SERVICE #########
    polkit.addRule(function(action, subject) {
      if (action.id == "org.freedesktop.systemd1.manage-units" &&
          subject.isInGroup("${group}") &&
          action.lookup("unit") == "${mount-service-name}.service" &&
          (action.lookup("verb") == "start" || action.lookup("verb") == "stop")) {
        return polkit.Result.YES;
      }
    });

    ####### POLKIT RULES UMOUNT SERVICE #########
    polkit.addRule(function(action, subject) {
      if (action.id == "org.freedesktop.systemd1.manage-units" &&
          subject.isInGroup("${group}") &&
          action.lookup("unit") == "${umount-service-name}.service" &&
          (action.lookup("verb") == "start" || action.lookup("verb") == "stop")) {
        return polkit.Result.YES;
      }
    });
  '';
}