{ config, lib, pkgs, ... }:
with lib;
{
  system.activationScripts.updateToc = {
    deps = [];
    text = ''
      echo "Updating Table of Contents..."
      echo "CURRENTLY DISABLED; FIXME"
      # ${pkgs.python3}/bin/python3 ${./generate-toc.py}
    '';
  };
}