{
  lib,
  pkgs,
  config,
  ...
}:
with lib; let
  cfg = config.roles.postgres.main;

  postgresqlPort = config.roles.postgres.default.postgresqlPort;

  mkDefaultUser = user: {
    name = user;
    ensureDBOwnership = true;
    ensureClauses = {};
  };
in {
  options.roles.postgres.main = {
    enable = mkEnableOption "main internal postgres configuration";

    authentication = mkOption {
      # multi line string
      type = types.str;
      default = ''
        #type database                  DBuser                      address                     auth-method         optional_ident_map
        local sameuser                  all                                                     peer                map=superuser_map
        host  all                       all
        host  replication               ${cfg.replUser}
        host  ${cfg.devUser}            ${cfg.devUser}
      '';
    };

    identMap = mkOption {
      type = types.str;
      default = ''
        # ArbitraryMapName systemUser DBUser
        superuser_map      root      postgres
        superuser_map      root      ${cfg.replUser}
        superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
        superuser_map      ${config.user.admin.name}     endoregClient
        superuser_map      postgres  postgres

        # Let other names login as themselves
        superuser_map      /^(.*)$   \1           
      '';
    };

    replUser = mkOption {
      type = types.str;
      default = "replUser";
    };

    testUser = mkOption {
      type = types.str;
      default = "testUser";
    };

    devUser = mkOption {
      type = types.str;
      default = "devUser";
    };

    lxClientUser = mkOption {
      type = types.str;
      default = "lxClientUser";
    };

    stagingUser = mkOption {
      type = types.str;
      default = "stagingUser";
    };

    productionUser = mkOption {
      type = types.str;
      default = "prodUser";
    };

  };


  config = mkIf cfg.enable {
    services.luxnix.postgresql.enable = true;

    roles.postgres.default.enable = true;
    # Allow port:
    networking.firewall.allowedTCPPorts = [ postgresqlPort ];

    services = {
      postgresql = {
        ensureDatabases = [
          "replication"
          cfg.replUser
          cfg.testUser
          cfg.devUser
          cfg.lxClientUser
          cfg.stagingUser
          cfg.productionUser
        ];

        ensureUsers = [
          (mkDefaultUser cfg.replUser)
          (mkDefaultUser cfg.testUser)
          (mkDefaultUser cfg.devUser)
          (mkDefaultUser cfg.lxClientUser)
          (mkDefaultUser cfg.stagingUser)
          (mkDefaultUser cfg.productionUser)
        ];
        
        # host  ${conf.keycloak-user}     ${conf.keycloak-user}       127.0.0.1/32                scram-sha-256 
        # host  ${conf.keycloak-user}     ${conf.keycloak-user}       ${conf.host-keycloak-ip}/32 scram-sha-256
        # host  replication               ${cfg.replUser}              ${conf.ip-backup}/32        scram-sha-256
        # host  ${conf.users.aglnet-base.name} ${conf.users.aglnet-base.name} 172.16.255.142/32 scram-sha-256
        
        authentication = lib.mkOverride 100 cfg.authentication;
        identMap = lib.mkOverride 100  cfg.identMap;
      };
    };




  };
}
