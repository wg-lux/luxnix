{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
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
in
{
  options.services.luxnix.ollama = {
    enable = mkBoolOpt false "Enable the Ollama service";
    acceleration = mkOpt (types.nullOr (
      types.enum [
        false
        "rocm"
        "cuda"
        "vulkan"
      ]
    )) false "Ollama hardware acceleration backend; false keeps this wrapper on CPU";
    enableOpenWebUi = mkBoolOpt false "Enable Open WebUI for Ollama";
    openWebUiPort = mkOpt types.port 8085 "Open WebUI port";
    enableModelBootstrap = mkBoolOpt false "Pull and create the default Ollama model";
  };

  config = mkIf cfg.enable (mkMerge [
    {
      services.ollama = {
        enable = true;
        acceleration = mkDefault cfg.acceleration;
        environmentVariables = {
          OLLAMA_KEEP_ALIVE = mkDefault "1m";
          OLLAMA_MAX_LOADED_MODELS = mkDefault "1";
          OLLAMA_NUM_PARALLEL = mkDefault "1";
        };
      };
    }

    (mkIf cfg.enableOpenWebUi {
      services.open-webui = {
        enable = true;
        port = cfg.openWebUiPort;
      };
    })

    (mkIf cfg.enableModelBootstrap {
      services.ollama.loadModels = [ "gemma4:e2b" ];

      systemd.services."ollama-create-lx-gemma4-e2b-json" = {
        description = "Create lx-anonymizer Gemma 4 E2B JSON Ollama model";
        after = [
          "ollama.service"
          "ollama-model-loader.service"
        ];
        requires = [
          "ollama.service"
          "ollama-model-loader.service"
        ];
        environment = config.systemd.services.ollama.environment;
        serviceConfig = {
          Type = "oneshot";
          DynamicUser = true;
          ExecStart = concatStringsSep " " [
            "${config.services.ollama.package}/bin/ollama"
            "create"
            "lx-gemma4-e2b-json"
            "-f"
            "${lxGemma4JsonModelfile}"
          ];
        };
        wantedBy = [ "multi-user.target" ];
      };
    })
  ]);
}
