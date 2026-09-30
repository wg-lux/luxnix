{ lib, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption {
            type = types.str;
            default = "lx-annotate.local";
          };
          port = mkOption {
            type = types.port;
            default = 5433;
          };
          name = mkOption {
            type = types.str;
            default = "lxAnnotateLocal";
          };
          user = mkOption {
            type = types.str;
            default = "lxAnnotateLocal";
          };
          passwordFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
            description = "Deprecated legacy maintenance-password path; not used for the local application role";
          };
          sslMode = mkOption {
            type = types.str;
            default = "prefer";
          };
          endoregLocalUserPasswordFile = mkOption {
            type = types.path;
            default = "/var/lib/postgresql/endoregDbLocal.password";
            description = "Canonical protected file containing the endoregDbLocal application password";
          };
        };
      };
      default = { };
      description = "Database configuration options";
    };
  };
}
