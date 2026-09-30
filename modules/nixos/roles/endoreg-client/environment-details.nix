{ lib }:
with lib;
{
  hfHome = mkOption {
    type = types.nullOr types.str;
    default = null;
    description = "Default HuggingFace home directory. When null, derived from the service user home.";
  };

  hfHubCache = mkOption {
    type = types.nullOr types.str;
    default = null;
    description = "Default HuggingFace hub cache directory. When null, derived from the service user home.";
  };

  transformersCache = mkOption {
    type = types.nullOr types.str;
    default = null;
    description = "Default transformers cache directory. When null, derived from the service user home.";
  };

  hfHubEnableTransfer = mkOption {
    type = types.bool;
    default = true;
    description = "Whether to enable HF_HUB_ENABLE_HF_TRANSFER by default.";
  };

  ollamaModelsDir = mkOption {
    type = types.nullOr types.str;
    default = null;
    description = "Default Ollama models directory. When null, derived from the service user home.";
  };

  ollamaKeepAlive = mkOption {
    type = types.str;
    default = "4h";
    description = "Default keep-alive duration for Ollama.";
  };
}
