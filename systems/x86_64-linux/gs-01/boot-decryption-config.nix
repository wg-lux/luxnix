{
  # # Ensure necessary kernel modules for USB and LUKS
  # boot.initrd.availableKernelModules = [ "dm-crypt" "sd_mod" "usb_storage" ];

  # # Use the usb-device as keyFile, with offset and size defined above.
  # # Adjust the LUKS device naming to match the updated configuration.
  # boot.initrd.luks.devices."cryptroot0" = {
  #   keyFile        = usb-device;
  #   keyFileOffset  = offset-b;
  #   keyFileSize    = keyfile-size;
  #   preLVM         = true;
  #   keyFileTimeout = 10;
  # };
  # boot.initrd.luks.devices."cryptroot1" = {
  #   keyFile        = usb-device;
  #   keyFileOffset  = offset-b;
  #   keyFileSize    = keyfile-size;
  #   preLVM         = true;
  #   keyFileTimeout = 10;
  # };
  # boot.initrd.luks.devices."cryptroot2" = {
  #   keyFile        = usb-device;
  #   keyFileOffset  = offset-b;
  #   keyFileSize    = keyfile-size;
  #   preLVM         = true;
  #   keyFileTimeout = 10;
  # };
}
