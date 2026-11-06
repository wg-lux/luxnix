{ config, lib, ... }:
let
  inherit (lib) mkOption types;
  cfg = config.services.luxnix.lxAnnotateLocal;
  role = config.roles.endoreg-client;
  shared = import ../../../roles/endoreg-client/database.nix {
    inherit lib;
    strictSslMode = false;
  };
  schema = shared.options;
  localDatabase = config.roles.postgres.default;
  aliases = {
    host = "postgresHost";
    port = "postgresPort";
  };
  endpoints = lib.mapAttrs (
    field: alias:
    let
      external = cfg.runtime.externalServices.${alias};
      fallback =
        if role.enable then
          role.database.${field}
        else if field == "port" then
          localDatabase.postgresqlPort
        else
          schema.${field}.default;
    in
    if external != null && (!role.enable || fallback == schema.${field}.default) then
      external
    else
      fallback
  ) aliases;
  defaults = endpoints // {
    name = localDatabase.defaultDbName;
    user = localDatabase.defaultDbName;
    applicationPasswordFile = role.database.applicationPasswordFile;
  };
in
{
  options.services.luxnix.lxAnnotateLocal.database = mkOption {
    type = types.submodule {
      inherit (shared) imports;
      # The client schema owns common types/defaults; the service adapts defaults.
      options =
        lib.mapAttrs (
          name: option: option // lib.optionalAttrs (defaults ? ${name}) { default = defaults.${name}; }
        ) schema
        // {
          ownership = mkOption {
            type = types.enum [
              "local"
              "external"
            ];
            default = if cfg.runtime.externalServices.postgresHost == null then "local" else "external";
            description = "Database provisioner, independent of address. Legacy external endpoints default to external; managed loopback must explicitly select local.";
          };
        };
    };
    default = { };
    description = "Database configuration options";
  };
  config = {
    # Preserve the role adapter's mkDefault priority, including explicit overrides.
    services.luxnix.lxAnnotateLocal.database = lib.mkIf role.enable (
      lib.mapAttrs (_: lib.mkDefault) endpoints
    );
    assertions = lib.optionals cfg.enable (
      lib.mapAttrsToList (field: alias: {
        assertion =
          (
            cfg.runtime.externalServices.${alias} == null
            || cfg.runtime.externalServices.${alias} == cfg.database.${field}
          )
          && (
            !role.enable
            || role.database.${field} == schema.${field}.default
            || role.database.${field} == cfg.database.${field}
          );
        message = "LX-Annotate database.${field} conflicts with runtime.externalServices.${alias} or a custom roles.endoreg-client.database.${field}.";
      }) aliases
    );
  };
}
