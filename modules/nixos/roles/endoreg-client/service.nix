{ lib }:
with lib;
{
  workers = mkOption {
    type = types.int;
    default = 1;
    description = "Number of worker processes for the API service";
  };

  maxRequests = mkOption {
    type = types.int;
    default = 1000;
    description = "Maximum requests per worker before restart";
  };

  timeout = mkOption {
    type = types.int;
    default = 30;
    description = "Request timeout in seconds";
  };

  keepAlive = mkOption {
    type = types.int;
    default = 60;
    description = "Keep-alive timeout in seconds";
  };

  extraEnvironment = mkOption {
    type = types.attrsOf types.str;
    default = { };
    description = "Additional environment variables for the service";
    example = {
      REDIS_URL = "redis://localhost:6379/0";
      CELERY_BROKER_URL = "redis://localhost:6379/1";
    };
  };
}
