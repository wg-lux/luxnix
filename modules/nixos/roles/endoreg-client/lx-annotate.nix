{ lib }:
with lib;
{
  enable = mkOption {
    type = types.bool;
    default = true;
    description = "Enable the lx-annotate-local service on endoreg clients.";
  };

  debug = mkOption {
    type = types.submodule {
      options = {
        enable = mkOption {
          type = types.bool;
          default = false;
          description = "Enable verbose debug output for the lx-annotate-local service.";
        };
      };
    };
    default = { };
    description = "Debug configuration for lx-annotate-local.";
  };

  source = mkOption {
    type = types.submodule {
      options = {
        url = mkOption {
          type = types.str;
          default = "https://github.com/wg-lux/lx-annotate";
          description = "Git repository URL for the lx-annotate application.";
        };

        branch = mkOption {
          type = types.str;
          default = "erc";
          description = "Git branch to checkout for lx-annotate.";
        };

        updateOnBoot = mkOption {
          type = types.bool;
          default = true;
          description = "Whether to update the lx-annotate repository on service start.";
        };
      };
    };
    default = { };
    description = "Repository configuration for lx-annotate.";
  };

  django = mkOption {
    type = types.submodule {
      options = {
        djangoModule = mkOption {
          type = types.str;
          default = "lx_annotate";
          description = "Python module containing the lx-annotate Django project.";
        };

        confDir = mkOption {
          type = types.nullOr types.str;
          default = null;
          description = "Override for the lx-annotate configuration directory. Uses the shared API value when null.";
        };

        confTemplateDir = mkOption {
          type = types.nullOr types.str;
          default = null;
          description = "Override for the lx-annotate configuration template directory. Uses the shared API value when null.";
        };

        assetDir = mkOption {
          type = types.nullOr types.str;
          default = null;
          description = "Override for the lx-annotate asset directory. Uses the shared API value when null.";
        };
      };
    };
    default = { };
    description = "Overrides for lx-annotate Django-specific paths.";
  };

  runtime = mkOption {
    type = types.submodule {
      options = {
        limits = mkOption {
          type = types.submodule {
            options = {
              memoryMax = mkOption {
                type = types.str;
                default = "8G";
                description = "MemoryMax limit applied to the lx-annotate-local service.";
              };

              cpuQuota = mkOption {
                type = types.str;
                default = "800%";
                description = "CPUQuota assigned to the lx-annotate-local service.";
              };
            };
          };
          default = { };
          description = "Resource limit configuration for lx-annotate-local.";
        };

        environment = mkOption {
          type = types.submodule {
            options = {
              hfHome = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Override HuggingFace home directory for lx-annotate.";
              };

              hfHubCache = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Override HuggingFace hub cache directory for lx-annotate.";
              };

              transformersCache = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Override transformers cache directory for lx-annotate.";
              };

              hfHubEnableTransfer = mkOption {
                type = types.nullOr types.bool;
                default = null;
                description = "Override HF_HUB_ENABLE_HF_TRANSFER for lx-annotate.";
              };

              ollamaModelsDir = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Override Ollama models directory for lx-annotate.";
              };

              ollamaKeepAlive = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Override Ollama keep-alive duration for lx-annotate.";
              };
            };
          };
          default = { };
          description = "Environment variable overrides for lx-annotate-local.";
        };
      };
    };
    default = { };
    description = "Runtime configuration for lx-annotate-local.";
  };
}
