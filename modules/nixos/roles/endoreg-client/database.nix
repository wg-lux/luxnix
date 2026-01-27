{ lib }:
with lib;
{
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

  passwordFile = mkOption {
    type = types.path;
    default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
    description = "Path to file containing database password";
  };

  endoregLocalUserPasswordFile = mkOption {
    type = types.path;
    default = "/var/lib/postgresql/endoregDbLocal.password";
    description = "Path to file containing endoregDbLocal user password";
  };

  sslMode = mkOption {
    type = types.enum [
      "disable"
      "allow"
      "prefer"
      "require"
      "verify-ca"
      "verify-full"
    ];
    default = "prefer";
    description = "PostgreSQL SSL mode";
  };
}
