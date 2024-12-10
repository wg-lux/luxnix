{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.settings;
in {
  options.user.settings = {
    mutable = mkBoolOpt false "Enable mutable user settings";
  };

  config = {
    users.mutableUsers = cfg.mutable;
  };
}