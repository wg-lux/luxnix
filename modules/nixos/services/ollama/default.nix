{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.ollama;
  lxGemma4JsonModelfile = pkgs.writeText "lx-gemma4-e2b-json.Modelfile" ''
    FROM gemma4:e2b

    PARAMETER temperature 0
    PARAMETER num_ctx 8192
    PARAMETER num_predict 256

    SYSTEM """
    Return exactly one JSON object and nothing else.
    Do not return markdown, comments, explanations, or reasoning.
    Do not include <think> blocks.
    Use null for unknown values.
    Only use these keys:
    patient_first_name
    patient_last_name
    patient_dob
    casenumber
    examination_date
    Normalize dates to YYYY-MM-DD when possible.
    Do not invent values.
    """
  '';
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
        ExecStart = "${config.services.ollama.package}/bin/ollama pull gemma4:e2b";
        User = "ollama";
      };
      wantedBy = [ "multi-user.target" ];
    };

    systemd.services."ollama-create-lx-gemma4-e2b-json" = {
      description = "Create lx-anonymizer Gemma 4 E2B JSON Ollama model";
      after = [
        "ollama.service"
        "ollama-pull-lx-anonymizer-default-model.service"
      ];
      requires = [
        "ollama.service"
        "ollama-pull-lx-anonymizer-default-model.service"
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = concatStringsSep " " [
          "${config.services.ollama.package}/bin/ollama"
          "create"
          "lx-gemma4-e2b-json"
          "-f"
          "${lxGemma4JsonModelfile}"
        ];
        User = "ollama";
      };
      wantedBy = [ "multi-user.target" ];
    };
  };
}
