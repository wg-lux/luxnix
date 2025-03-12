let
  usb-uuid = "00acbcc0-b74f-4442-9460-b2e2d4e5042d";
  usb-mountpoint = "/mnt/usb_key";
  usb-device = "/dev/disk/by-uuid/00acbcc0-b74f-4442-9460-b2e2d4e5042d";

  bs = 1;
  offset-m = 50;
  offset-b = 52428800;
  keyfile-size = 4096;
in
{ }
