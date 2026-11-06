{
  lib,
  strictSslMode ? true,
}:
with lib;
{
  # Keep the functional legacy name at the public boundary only.
  imports = [
    (mkAliasOptionModule [ "endoregLocalUserPasswordFile" ] [ "applicationPasswordFile" ])
  ];
  options = {
    host = mkOption {
      type = types.str;
      default = "localhost";
      description = "PostgreSQL database host";
    };

    port = mkOption {
      type = types.port;
      default = 5432;
      description = "PostgreSQL database port";
    };

    name = mkOption {
      type = types.str;
      default = "endoregDbLocal";
      description = "PostgreSQL database name";
    };

    user = mkOption {
      type = types.str;
      default = "endoregDbLocal";
      description = "PostgreSQL database user";
    };

    applicationPasswordFile = mkOption {
      type = types.path;
      default = "/var/lib/postgresql/endoregDbLocal.password";
      description = "Protected PostgreSQL application password file";
    };

    sslMode = mkOption {
      type =
        if strictSslMode then
          types.enum [
            "disable"
            "allow"
            "prefer"
            "require"
            "verify-ca"
            "verify-full"
          ]
        else
          types.str;
      default = "prefer";
      description = "PostgreSQL SSL mode";
    };
  };
}
