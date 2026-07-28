{ }:
{
  entrypoint =
    { cfg }:
    {
      config = {
        services.luxnix.lxAiLocal = {
          enable = cfg.lxAi;
          database = cfg.database;
          source.branch = "prototype";
          runtime.backboneCheckpointUrl = "https://drive.google.com/uc?export=download&id=1TvliEJ5JTQddIE3kNiGMQzWIe9Cq_7mx";
        };
      };
    };
}
