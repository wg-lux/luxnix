{ lib }:
{
  entrypoint =
    { lxAnnotateRole }:
    {
      config = {
        services.luxnix.fileMover.enable = lib.mkDefault lxAnnotateRole.enable;
      };
    };
}
