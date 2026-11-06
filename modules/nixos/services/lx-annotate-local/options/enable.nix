{ lib, ... }:
let
  inherit (lib.luxnix) mkBoolOpt;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    enable = mkBoolOpt false "Enable LxAnnotate Service";
  };
}
