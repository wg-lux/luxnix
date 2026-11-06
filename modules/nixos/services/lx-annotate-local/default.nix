{
  config,
  lib,
  pkgs,
  ...
}@args:
let
  runtimeContext = import ./runtime-context.nix { inherit config lib pkgs; };
  inherit (runtimeContext)
    cfg
    gs
    gsp
    sslCfg
    lxAnnotateRuntime
    ;

  moduleArgs = args // {
    inherit
      cfg
      gs
      gsp
      sslCfg
      ;
    inherit lxAnnotateRuntime;
  };
in
{
  imports = [
    (import ./options.nix moduleArgs)
    (import ./config.nix moduleArgs)
  ];
}
