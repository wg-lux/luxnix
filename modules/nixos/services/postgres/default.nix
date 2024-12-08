{
  config,
  lib,
  pkgs,
  ...
}:
#CHANGEME
with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.postgresql;
in {
  options.services.luxnix.postgresql = {
    enable = mkBoolOpt false "Enable postgresql";
  };

  config = mkIf cfg.enable {
    services = {
      postgresql = {
        enable = true;
        # TODO: look at using default postgres
        package = pkgs.postgresql_16_jit;
        extraPlugins = ps: with ps; [pgvecto-rs];
        settings = {
          shared_preload_libraries = ["vectors.so"];
          search_path = "\"$user\", public, vectors";
        };
      };
      postgresqlBackup = {
        enable = true;
        location = "/mnt/share/postgresql";
        backupAll = true;
        startAt = "*-*-* 10:00:00";
      };
    };
  };
}
