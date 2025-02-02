{
  lib,
  pkgs,
  config,
  ...
}:
with lib; let
  cfg = config.roles.postgres.main;

  postgresqlPort = config.roles.postgres.default.postgresqlPort;

  adminAuthKeys = config.users.users.${config.user.admin.name}.openssh.authorizedKeys.keys;
  allAuthKeys = adminAuthKeys ++ cfg.additionalPostgresAuthKeys;


in {
  options.roles.postgres.main = {
    enable = mkEnableOption "main internal postgres configuration";

    listen_addresses = mkOption {
      type = types.str;
      default = "localhost,127.0.0.1,${config.luxnix.generic-settings.vpnIp}";
    };

    additionalPostgresAuthKeys = mkOption {
      type = types.ListOf types.str;
      default = [];
      description = "Additional authorized keys for postgres user";
    };

  };


  config = mkIf cfg.enable {
    networking.firewall.allowedTCPPorts = [ postgresqlPort ];
    services.luxnix.postgresql.listen_addresses = cfg.listen_addresses;

    # Allow SSH Access for postgres user
    users.users = {
      postgres = {
        openssh.authorizedKeys.keys = allAuthKeys;
      };
    };
  
  };
}
