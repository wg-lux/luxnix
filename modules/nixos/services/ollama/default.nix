{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.services.luxnix.ollama;
  unstablePkgs = import inputs.nixpkgs-unstable {
    system = pkgs.stdenv.hostPlatform.system;
    config.allowUnfree = true;
  };
  unstableOllama =
    if cfg.acceleration == null then
      unstablePkgs.ollama
    else if cfg.acceleration == false then
      unstablePkgs.ollama-cpu
    else
      unstablePkgs.${"ollama-${cfg.acceleration}"};
  defaultCustomModels = {
    lx-gemma4-e2b-json = ''
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
  };
  sanitizeUnitName =
    replaceStrings
      [
        "/"
        ":"
        "."
        "@"
        " "
      ]
      [
        "-"
        "-"
        "-"
        "-"
        "-"
      ];
  modelLoaderUnits = optional (cfg.models != [ ]) "ollama-model-loader.service";
  customModelFiles = mapAttrs (
    modelName: modelfile: pkgs.writeText "ollama-${sanitizeUnitName modelName}.Modelfile" modelfile
  ) cfg.customModels;
  mkCustomModelService = modelName: modelfile: {
    description = "Create Ollama model ${modelName}";
    after = [ "ollama.service" ] ++ modelLoaderUnits;
    requires = [ "ollama.service" ] ++ modelLoaderUnits;
    environment = config.systemd.services.ollama.environment;
    serviceConfig = {
      Type = "oneshot";
      DynamicUser = true;
      ExecStart = escapeShellArgs [
        "${config.services.ollama.package}/bin/ollama"
        "create"
        modelName
        "-f"
        "${modelfile}"
      ];
    };
    wantedBy = [ "multi-user.target" ];
  };
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
    enableModelBootstrap = mkBoolOpt false "Pull configured Ollama models and create configured custom models";
    models = mkOpt (types.listOf types.str) [
      "gemma4:e2b"
    ] "Ollama model names to pull when model bootstrap is enabled";
    customModels =
      mkOpt (types.attrsOf types.lines) defaultCustomModels
        "Custom Ollama models to create when model bootstrap is enabled. Attribute names are model names and values are Modelfile contents.";
  };

  config = mkIf cfg.enable (mkMerge [
    {
      services.ollama = {
        enable = true;
        package = mkDefault unstableOllama;
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

    (mkIf cfg.enableModelBootstrap (mkMerge [
      (mkIf (cfg.models != [ ]) {
        services.ollama.loadModels = cfg.models;
      })

      (mkIf (cfg.customModels != { }) {
        systemd.services = mapAttrs' (
          modelName: modelfile:
          nameValuePair "ollama-create-${sanitizeUnitName modelName}" (
            mkCustomModelService modelName modelfile
          )
        ) customModelFiles;
      })
    ]))
  ]);
}
