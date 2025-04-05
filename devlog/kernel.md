# UDP Buffer Size

- Added:
  boot.kernel.sysctl."net.core.rmem_max" = 7500000;
  boot.kernel.sysctl."net.core.wmem_max" = 7500000;

  to modules/nixos/system/boot/default.nix
