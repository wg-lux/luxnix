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
  services.ollama.enable = true;
  services.open-webui.enable = true;
  services.open-webui.port = 8085;

  systemd.services."ollama-pull-lx-anonymizer-default-model" = {
    description = "Pull lx-anonymizer default Ollama model";
    after = [ "ollama.service" ];
    requires = [ "ollama.service" ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${config.services.ollama.package}/bin/ollama pull qwen2.5:7b-instruct";
      User = "ollama";
    };
    wantedBy = [ "multi-user.target" ];
  };
};

}
