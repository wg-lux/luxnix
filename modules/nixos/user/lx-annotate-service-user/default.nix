{ config, lib, pkgs, ... }:
with lib;
let
  userName = "lx-annotate-service-user";
  groupName = "lx-annotate-service";
  homeDir = "/var/lx-annotate-service-user";
in
{
  options.user.lx-annotate-service-user = {
    enable = mkEnableOption "Enable lx-annotate service user";
    name = mkOption { type = types.str; default = userName; };
    home = mkOption { type = types.path; default = homeDir; };
    group = mkOption { type = types.str; default = groupName; };
    uid = mkOption { type = types.int; default = 1051; };
    gid = mkOption { type = types.int; default = 1051; };
  };

  config = mkIf config.user.lx-annotate-service-user.enable {
    users.users.${userName} = {
      isSystemUser = true;
      home = homeDir;
      group = groupName;
      uid = 1051;
      shell = pkgs.zsh;
      description = "Service user for lx-annotate";
      createHome = true;
    };
    users.groups.${groupName} = {
      name = groupName;
      gid = 1051;
      members = [ userName ];
    };
  };
}
