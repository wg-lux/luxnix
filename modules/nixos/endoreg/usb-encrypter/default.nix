{
  config,
  inputs,
  pkgs,
  lib,
  ...
}:

with lib;
with lib.luxnix; let
  cfg = config.endoreg.usbEncrypter;

  # we need to find out what system we are working on (eg linux, darwin, ...)
  system = config.system.build.host.system;
  
in {
  options.endoreg.usbEncrypter = with types; {
    enable = mkBoolOpt false "Enable or disable the USB encrypter";
  };

  config = mkIf cfg.enable {
    environment.systemPackages = [
      inputs.endoreg-usb-encrypter.apps.encrypter
    ];
  };
  
}