{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.security.luxnix.local-users;
in {
  options.security.luxnix.local-users = {
    enable = mkBoolOpt false "Whether to use hashed pwd files for local users";
  };

  config = mkIf cfg.enable {
  };
}
