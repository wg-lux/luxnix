{ config, pkgs, lib, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
    ./boot-decryption-config.nix
    ./disks.nix
    ./luxnix.nix
  ];

  user = {
    admin= {
    name= "admin";
    };
    ansible.enable = true;
    settings.mutable = false;
  };

roles = {
    base-server.enable= true;
    aglnet.client.enable= true;
    ssh-access.dev-01.enable= true;
    ssh-access.dev-01.idEd25519= "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK";
    postgres.main.enable= true;
    postgres.main.authentication = ''


#type database                  DBuser                      address                     auth-method         optional_ident_map
local sameuser                  all                                                     peer                map=superuser_map
host  all                       all                172.16.255.106/32          scram-sha-256 map=superuser_map
host  replication               ${config.postgres.main.replUser}    172.16.255.106/32          scram-sha-256
host  ${config.postgres.main.devUser}            ${config.postgres.main.devUser}     172.16.255.106/32          scram-sha-256d
'';
    postgres.main.identMap = ''


# ArbitraryMapName systemUser DBUser
superuser_map      root      postgres
superuser_map      root      ${config.postgres.main.replUser}
superuser_map      ${config.user.admin.name}     ${config.user.admin.name}
superuser_map      ${config.user.admin.name}     endoregClient
superuser_map      postgres  postgres

# Let other names login as themselves
superuser_map      /^(.*)$   \1d
'';
    };

  services = {

};
}