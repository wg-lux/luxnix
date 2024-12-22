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
    backupLocation = mkOption {
      type = types.str;
      default = "/home/${config.user.admin.name}/postgresql-backup";
    };
  };

  config = mkIf cfg.enable {

    # tmpfile rule for backup directory
    systemd.tmpfiles.rules = [
      "d ${cfg.backupLocation} 0700 postgres postgres -"
    ];

    environment.systemPackages = with pkgs; [
      postgresql_16_jit
    ];

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
        location = "${cfg.backupLocation}";
        backupAll = true;
        startAt = "*-*-* 10:00:00";
      };
    };
  };
}
