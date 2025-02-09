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
  gs = config.luxnix.generic-settings;
  gsp = gs.postgres;

  adminName = config.user.admin.name;
  

  defaults = config.roles.postgres.default;

  enableKeycloak = config.roles.keycloakHost.enable;
  keycloakDbUser = config.roles.keycloakHost.dbUsername;

  remoteAdmin = gsp.remote.admin.enable;
  adminVpnIp = gsp.remote.admin.vpnIp;

  auth = ''
      #type database                  DBuser                      address                     auth-method         optional_ident_map
      local all                       postgres                                                trust
      local all                       postgres                                                peer                map=superuser_map
      local sameuser                  all                                                     peer                map=superuser_map
      host  all                       all                         127.0.0.1/32                scram-sha-256
      host  replication               ${defaults.replUser}        127.0.0.1/32                scram-sha-256 
      host  ${defaults.devUser}            ${defaults.devUser}    127.0.0.1/32                scram-sha-256 
    '' 
    + cfg.extraAuthentication
    + (if enableKeycloak then ''
      
      host ${keycloakDbUser} ${keycloakDbUser} 127.0.0.1/32 scram-sha-256
      host ${keycloakDbUser} ${keycloakDbUser} ::1/128 scram-sha-256
      '' else "")
    + (if remoteAdmin then "\nhost all all ${adminVpnIp}/32 scram-sha-256" else "")
    + (if remoteAdmin then "\nhost ${defaults.devUser} ${defaults.devUser} ${adminVpnIp}/32 scram-sha-256" else "") 
    + (if remoteAdmin then "\nhost  all postgres ${adminVpnIp}/32 scram-sha-256" else "")
    + (if defaults.enable then "\nhost ${defaults.defaultDbName} ${defaults.defaultDbName} 127.0.0.1/32 scram-sha-256" else "")

    ;

    

  identMap = ''
    # ArbitraryMapName systemUser DBUser
        superuser_map      root      postgres
        superuser_map      root      ${defaults.replUser}
        superuser_map      ${adminName}     ${adminName}
        superuser_map      ${adminName}     endoregClient
        superuser_map      postgres  postgres

        # Let other names login as themselves
        superuser_map      /^(.*)$   \1           
    ''
    + cfg.extraIdentMap;

in {
  options.services.luxnix.postgresql = {
    enable = mkBoolOpt false "Enable postgresql";
    backupLocation = mkOption {
      type = types.str;
      default = "/home/${adminName}/postgresql-backup";
    };

    extraAuthentication = mkOption {
      # multi line string
      type = types.str;
      default = '''';
    };

    extraIdentMap = mkOption {
      type = types.str;
      default = '''' ;
    };

    listen_addresses = mkOption {
      type = types.str;
      default = "localhost,127.0.0.1";
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
        settings = {
          listen_addresses = lib.mkForce cfg.listen_addresses;
        };
        # TODO: look at using default postgres
        package = pkgs.postgresql_16_jit;
        extensions = ps: with ps; [pgvecto-rs];
        settings = {
          shared_preload_libraries = ["vectors.so"];
          search_path = "\"$user\", public, vectors";
        };
        authentication = lib.mkOverride 10 auth;
        identMap = lib.mkOverride 10 identMap;
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
