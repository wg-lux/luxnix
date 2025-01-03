let
  usb-uuid = "50bfb364-e2a1-435d-ab8a-c5ba5e4b8f30";
  usb-mountpoint = "/mnt/usb_key";
  usb-device = "/dev/disk/by-uuid/50bfb364-e2a1-435d-ab8a-c5ba5e4b8f30";

  bs = 1;
  offset-m = 50;
  offset-b = 52428800;
  keyfile-size = 4096;
in {
  # Ensure necessary kernel modules for USB and LUKS
  boot.initrd.availableKernelModules = [ "dm-crypt" "sd_mod" "usb_storage" ];

  # 'cryptroot' is defined by disko as the name of the LUKS container.
  # Use the usb-device as keyFile, with offset and size defined above.
  boot.initrd.luks.devices."cryptroot" = {
    keyFile            = usb-device;
    keyFileOffset      = offset-b;
    keyFileSize        = keyfile-size;
    preLVM             = true;
    keyFileTimeout = 10; # if no prompt is displayed, try pressing "Esc"
  };
}
