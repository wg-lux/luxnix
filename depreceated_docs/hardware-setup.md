# Hardware Setup

The hardware of LuxNix is set up in the 

## Boot Decryption Stick

The module 

```
{
  pkgs,
  lib,
  ...
}@inputs: 
  let
    sensitiveHdd = import ./sensitive-hdd.nix {};

    extraImports = [
      ./boot-decryption-config.nix
    ];

  in
{
  imports = [
    ./hardware-configuration.nix
    ./disks.nix
  ]++extraImports;
# .....
}
```nix