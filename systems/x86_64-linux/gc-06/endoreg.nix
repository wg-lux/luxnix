{config, ...}@inputs: {
  endoreg = {
    sensitiveStorage = {
      enable = false;
      partitionConfigurations = {
        # Partition dropoff
        "dropoff" = {
          label = "dropoff";
          device = "/dev/disk/by-uuid/f869c662-f23f-4799-8e5f-21bb89558b3d";
          device-by-label = "/dev/disk/by-label/dropoff";
          mountPoint = "/mnt/sensitive-hdd-mount/dropoff";
          uuid = "f869c662-f23f-4799-8e5f-21bb89558b3d";
          luks-uuid = "a1a6f755-82d4-4d28-b3a9-14d4006ce5f1";
          luks-device = "/dev/disk/by-uuid/a1a6f755-82d4-4d28-b3a9-14d4006ce5f1";
          fsType = "ext4";
        };
        # Partition processing
        "processing" = {
          label = "processing";
          device = "/dev/disk/by-uuid/b4a67808-1b50-4e9b-899d-d2023d52f467";
          device-by-label = "/dev/disk/by-label/processing";
          mountPoint = "/mnt/sensitive-hdd-mount/processing";
          uuid = "b4a67808-1b50-4e9b-899d-d2023d52f467";
          luks-uuid = "a0b86635-7142-4057-bdb5-dfc64e4db64e";
          luks-device = "/dev/disk/by-uuid/a0b86635-7142-4057-bdb5-dfc64e4db64e";
          fsType = "ext4";
        };
        # Partition processed
        "processed" = {
          label = "processed";
          device = "/dev/disk/by-uuid/39543afc-c76f-4241-8d1d-4eac7a959134";
          device-by-label = "/dev/disk/by-label/processed";
          mountPoint = "/mnt/sensitive-hdd-mount/processed";
          uuid = "39543afc-c76f-4241-8d1d-4eac7a959134";
          luks-uuid = "df869024-48cd-4686-b894-94ab1fefa726";
          luks-device = "/dev/disk/by-uuid/df869024-48cd-4686-b894-94ab1fefa726";
          fsType = "ext4";
        };
      };
    };
  };
}