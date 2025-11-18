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
    enable = mkOption {
      type = types.bool;
      default = false;
      description = "Enable ollama and web ui";
    };
  };

  config = mkIf cfg.enable {
    services.ollama.enable = true;
    services.open-webui.enable = true;
    services.open-webui.port = 8085;

    systemd.services."ollama-pull-deepseek" = {
      description = "Pull deepseek-r1 Ollama model";
      after = [ "ollama.service" ];
      requires = [ "ollama.service" ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${config.services.ollama.package}/bin/ollama pull deepseek-r1";
        User = "ollama";
      };
      wantedBy = [ "multi-user.target" ];
    };
};

}
