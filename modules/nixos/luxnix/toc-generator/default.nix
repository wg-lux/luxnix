{ config, lib, pkgs, ... }:
with lib;
{
  system.activationScripts.updateToc = {
    deps = [];
    text = ''
      echo "Updating Table of Contents..."
      ${pkgs.python3}/bin/python3 ${./generate-toc.py}
    '';
  };
}