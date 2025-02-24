let
  usb-uuid = "c5f719ff-dcc7-4e6d-950e-ed12cf3b21af";
  usb-mountpoint = "/mnt/usb_key";
  usb-device = "/dev/disk/by-uuid/c5f719ff-dcc7-4e6d-950e-ed12cf3b21af";

  bs = 1;
  offset-m = 50;
  offset-b = 52428800;
  keyfile-size = 4096;
in
{ }
