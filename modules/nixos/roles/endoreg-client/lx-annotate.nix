{ lib }:
with lib;
let
  workerPoolType = types.submodule {
    options = {
      concurrency = mkOption {
        type = types.ints.positive;
        default = 1;
        description = "Celery worker concurrency for this workload pool.";
      };
      maxTasksPerChild = mkOption {
        type = types.ints.positive;
        default = 1;
        description = "Maximum Celery tasks each child process handles before recycling.";
      };
      memoryHigh = mkOption {
        type = types.str;
        default = "1G";
        description = "MemoryHigh limit applied to this Celery workload pool.";
      };
      memoryMax = mkOption {
        type = types.str;
        default = "2G";
        description = "MemoryMax limit applied to this Celery workload pool.";
      };
      cpuQuota = mkOption {
        type = types.str;
        default = "35%";
        description = "CPUQuota assigned to this Celery workload pool.";
      };
      nice = mkOption {
        type = types.int;
        default = 15;
        description = "Systemd Nice value for this Celery workload pool.";
      };
      oomScoreAdjust = mkOption {
        type = types.int;
        default = 750;
        description = "OOMScoreAdjust value for this Celery workload pool.";
      };
    };
  };
  frameExtractionWorkerType = types.submodule {
    options = {
      mode = mkOption {
        type = types.enum [
          "maintenance-window"
          "always"
          "manual"
        ];
        default = "always";
        description = "Scheduling mode for the dedicated FFmpeg frame extraction Celery worker.";
      };

      onCalendar = mkOption {
        type = types.str;
        default = "*-*-* 22:00:00";
        description = "systemd OnCalendar schedule used when frame extraction runs in maintenance-window mode.";
      };

      runtimeMaxSec = mkOption {
        type = types.str;
        default = "7h";
        description = "Maximum runtime for one maintenance-window frame extraction worker activation.";
      };

      timeoutStopSec = mkOption {
        type = types.str;
        default = "45min";
        description = "Grace period for stopping the frame extraction worker before systemd sends a final kill signal.";
      };

      randomizedDelaySec = mkOption {
        type = types.str;
        default = "5m";
        description = "Randomized delay applied to the maintenance-window timer.";
      };

      persistentTimer = mkOption {
        type = types.bool;
        default = true;
        description = "Whether missed maintenance-window timer activations should run after boot.";
      };
    };
  };
  inferenceWorkerType = types.submodule {
    options = {
      mode = mkOption {
        type = types.enum [
          "always"
          "manual"
        ];
        default = "always";
        description = "Scheduling mode for the dedicated AI temporal inference Celery worker.";
      };

      cudaVisibleDevices = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Optional CUDA_VISIBLE_DEVICES value exported to the inference worker.";
      };
    };
  };
  trainingWorkerType = types.submodule {
    options = {
      mode = mkOption {
        type = types.enum [
          "always"
          "manual"
        ];
        default = "manual";
        description = "Scheduling mode for the dedicated GPU model-training Celery worker.";
      };

      cudaVisibleDevices = mkOption {
        type = types.str;
        default = "0";
        description = "CUDA_VISIBLE_DEVICES value exported to the model-training worker.";
      };
    };
  };
  celeryBrokerType = types.submodule {
    options = {
      requireSecureTransport = mkOption {
        type = types.bool;
        default = false;
        description = "Require TLS-equivalent secure transport for Celery broker connections.";
      };

      secureTransportConfirmed = mkOption {
        type = types.bool;
        default = false;
        description = "Operator acknowledgement that the configured broker transport is protected outside the URL scheme.";
      };
    };
  };
in
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
          default = "test";
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
        modelTrainingStagingRoot = mkOption {
          type = types.str;
          default = "/mnt/fast-nvme-cache/endoreg-training";
          description = "Ephemeral local staging root used by model-training jobs.";
        };

        commands = mkOption {
          type = types.submodule {
            options = {
              web = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/daphne -b \"$DJANGO_HOST\" -p \"$DJANGO_PORT\" lx_annotate.asgi:application";
                description = "Wheel-mode command used to run the lx-annotate web server.";
              };

              migrate = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django migrate --noinput --settings=lx_annotate.settings.settings_prod";
                description = "Wheel-mode command used to run lx-annotate database migrations.";
              };

              loadBaseData = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django load_base_db_data --settings=lx_annotate.settings.settings_prod";
                description = "Wheel-mode command used to load lx-annotate base data.";
              };

              fileWatcher = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django run_filewatcher --settings=lx_annotate.settings.settings_prod \${LX_ANNOTATE_FILEWATCHER_ARGS:-}";
                description = "Wheel-mode command used to run the lx-annotate file watcher.";
              };

              fileWatcherOnce = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Optional one-shot wheel-mode file watcher command. Defaults to runtime.commands.fileWatcher when unset.";
              };

              exportFrames = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/export-frames";
                description = "Wheel-mode command used to export annotated frames.";
              };

              celeryWorker = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/celery -A lx_annotate.celery:app worker --loglevel=INFO";
                description = "Wheel-mode command used to run the lx-annotate Celery worker.";
              };

              sapImport = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django import_sap_ish_zip --settings=lx_annotate.settings.settings_prod";
                description = "Base wheel-mode command for SAP import; the wrapper appends the ZIP and output directory.";
              };

              mediaMigration = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django migrate_media_storage --settings=lx_annotate.settings.settings_prod";
                description = "Base wheel-mode command for media and streamable storage migration.";
              };

              transcodeVideo = mkOption {
                type = types.nullOr types.str;
                default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django transcode_video --settings=lx_annotate.settings.settings_prod";
                description = "Base wheel-mode command for move-my-files video transcode fallback.";
              };
            };
          };
          default = { };
          description = "Wheel-mode auxiliary service commands for lx-annotate-local.";
        };

        limits = mkOption {
          type = types.submodule {
            options = {
              memoryHigh = mkOption {
                type = types.str;
                default = "4G";
                description = "MemoryHigh limit applied to the lx-annotate-local service.";
              };

              memoryMax = mkOption {
                type = types.str;
                default = "6G";
                description = "MemoryMax limit applied to the lx-annotate-local service.";
              };

              cpuQuota = mkOption {
                type = types.str;
                default = "50%";
                description = "CPUQuota assigned to the lx-annotate-local service.";
              };
            };
          };
          default = { };
          description = "Resource limit configuration for lx-annotate-local.";
        };

        workerLimits = mkOption {
          type = types.submodule {
            options = {
              memoryHigh = mkOption {
                type = types.str;
                default = "1G";
                description = "MemoryHigh limit applied to the lx-annotate Celery worker.";
              };

              memoryMax = mkOption {
                type = types.str;
                default = "2G";
                description = "MemoryMax limit applied to the lx-annotate Celery worker.";
              };

              cpuQuota = mkOption {
                type = types.str;
                default = "35%";
                description = "CPUQuota assigned to the lx-annotate Celery worker.";
              };
            };
          };
          default = { };
          description = "Resource limit configuration for the lx-annotate Celery worker.";
        };

        workerPools = mkOption {
          type = types.submodule {
            options = {
              pipeline = mkOption {
                type = workerPoolType;
                default = {
                  concurrency = 1;
                  maxTasksPerChild = 1;
                  memoryHigh = "2G";
                  memoryMax = "4G";
                  cpuQuota = "45%";
                  nice = 16;
                  oomScoreAdjust = 800;
                };
                description = "Celery pool for upload/import/anonymization pipeline work.";
              };
              frameExtraction = mkOption {
                type = workerPoolType;
                default = {
                  concurrency = 1;
                  maxTasksPerChild = 1;
                  memoryHigh = "3G";
                  memoryMax = "5G";
                  cpuQuota = "55%";
                  nice = 18;
                  oomScoreAdjust = 850;
                };
                description = "Celery pool for FFmpeg frame extraction and post-validation rebuilds.";
              };
              inference = mkOption {
                type = workerPoolType;
                default = {
                  concurrency = 1;
                  maxTasksPerChild = 1;
                  memoryHigh = "12G";
                  memoryMax = "16G";
                  cpuQuota = "250%";
                  nice = 10;
                  oomScoreAdjust = 350;
                };
                description = "Celery pool for AI temporal inference jobs.";
              };
              training = mkOption {
                type = workerPoolType;
                default = {
                  concurrency = 1;
                  maxTasksPerChild = 1;
                  memoryHigh = "24G";
                  memoryMax = "32G";
                  cpuQuota = "400%";
                  nice = 5;
                  oomScoreAdjust = 200;
                };
                description = "Celery pool for single-GPU model training jobs.";
              };
              maintenance = mkOption {
                type = workerPoolType;
                default = {
                  concurrency = 1;
                  maxTasksPerChild = 100;
                  memoryHigh = "1G";
                  memoryMax = "2G";
                  cpuQuota = "25%";
                  nice = 12;
                  oomScoreAdjust = 700;
                };
                description = "Celery pool for default and maintenance queues.";
              };
            };
          };
          default = { };
          description = "Queue-specific Celery worker pools for load-balancing heavy media jobs.";
        };

        frameExtractionWorker = mkOption {
          type = frameExtractionWorkerType;
          default = { };
          description = "Scheduling policy for the dedicated FFmpeg frame extraction Celery worker.";
        };

        inferenceWorker = mkOption {
          type = inferenceWorkerType;
          default = { };
          description = "Scheduling policy for the dedicated AI temporal inference Celery worker.";
        };

        trainingWorker = mkOption {
          type = trainingWorkerType;
          default = { };
          description = "Scheduling policy for the dedicated GPU model-training Celery worker.";
        };

        externalServices = mkOption {
          type = types.submodule {
            options = {
              redisUrl = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Optional external Redis/Celery broker URL for lx-annotate.";
              };

              postgresHost = mkOption {
                type = types.nullOr types.str;
                default = null;
                description = "Optional external PostgreSQL host for lx-annotate.";
              };

              postgresPort = mkOption {
                type = types.nullOr types.port;
                default = null;
                description = "Optional external PostgreSQL port for lx-annotate.";
              };
            };
          };
          default = { };
          description = "External service endpoints for cluster-oriented lx-annotate deployments.";
        };

        celeryBroker = mkOption {
          type = celeryBrokerType;
          default = { };
          description = "Celery broker transport security controls.";
        };

        clustered = mkOption {
          type = types.submodule {
            options = {
              enable = mkOption {
                type = types.bool;
                default = false;
                description = "Enable cluster-readiness guardrails for lx-annotate.";
              };

              sharedStorage = mkOption {
                type = types.bool;
                default = false;
                description = "Acknowledge that lx-annotate runtime data is backed by shared storage.";
              };

              sharedMasterKeyFile = mkOption {
                type = types.nullOr types.path;
                default = null;
                description = "Shared workload master key file for clustered lx-annotate deployments.";
              };
            };
          };
          default = { };
          description = "Cluster-readiness settings for lx-annotate.";
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
