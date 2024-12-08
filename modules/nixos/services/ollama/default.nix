{
  config,
  lib,
  ...
}:
with lib; 
with lib.luxnix; let
  cfg = config.services.luxnix.ollama;
in {
  options.services.luxnix.ollama = {
    enable = mkBoolOpt false "Enable ollama and web ui";
  };

  config = mkIf cfg.enable {
    services.ollama = {
      enable = true;
    };

    services.open-webui = {
      enable = true;
      port = 8085;
    };
  };
}
