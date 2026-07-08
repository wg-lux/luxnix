{ lib }:
{
  entrypoint =
    { config }:
    {
      config = {
        services.luxnix.endoregDbApiLocal.enable = lib.mkIf (!config.roles.endoreg-db-central-01.enable) (
          lib.mkForce false
        );
      };
    };
}
