{ lib }:
let
  inherit (lib) mkOption types;

  resourceLimitsType = types.submodule {
    options = {
      memoryHigh = mkOption {
        type = types.str;
        default = "4G";
        description = "MemoryHigh limit applied to the primary lx-annotate-local service.";
      };

      memoryMax = mkOption {
        type = types.str;
        default = "6G";
        description = "MemoryMax limit applied to the primary lx-annotate-local service.";
      };

      cpuQuota = mkOption {
        type = types.str;
        default = "50%";
        description = "CPUQuota assigned to the primary lx-annotate-local service.";
      };
    };
  };
  workerLimitsType = types.submodule {
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
      cpuWeight = mkOption {
        type = types.ints.between 1 10000;
        default = 100;
        description = "CPUWeight assigned to this Celery workload pool.";
      };
      ioWeight = mkOption {
        type = types.ints.between 1 10000;
        default = 100;
        description = "IOWeight assigned to this Celery workload pool.";
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
  ffmpegWorkerType = types.submodule {
    options = {
      mode = mkOption {
        type = types.enum [
          "always"
          "manual"
        ];
        default = "always";
        description = "Scheduling mode for the low-priority FFmpeg media Celery worker.";
      };
      timeoutStopSec = mkOption {
        type = types.str;
        default = "6h15min";
        description = "Warm-shutdown grace period for an active FFmpeg media task before systemd may send a final kill signal.";
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
  llmInferenceWorkerType = types.submodule {
    options = {
      mode = mkOption {
        type = types.enum [
          "always"
          "manual"
        ];
        default = "manual";
        description = "Scheduling mode for the dedicated Ollama-backed LLM inference Celery worker.";
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
  clusteredType = types.submodule {
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
  externalServicesType = types.submodule {
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
  runtimeIntakeDirsType = types.submodule {
    options = {
      importRoot = mkOption {
        type = types.str;
        default = "data/import";
        description = "Runtime intake root below runtime.encryptedDataDir.";
      };
      video = mkOption {
        type = types.str;
        default = "data/import/video_import";
        description = "Video intake directory exported as WATCHER_VIDEO_DIR.";
      };
      report = mkOption {
        type = types.str;
        default = "data/import/report_import";
        description = "Report intake directory exported as WATCHER_REPORT_DIR.";
      };
      preanonymized = mkOption {
        type = types.str;
        default = "data/import/preanonymized_import";
        description = "Preanonymized intake directory exported as WATCHER_PREANONYMIZED_DIR.";
      };
      sap = mkOption {
        type = types.str;
        default = "data/import/sap_import";
        description = "SAP IS-H ZIP drop directory.";
      };
      sapProcessed = mkOption {
        type = types.str;
        default = "data/import/sap_import_processed";
        description = "Directory where successfully converted SAP IS-H ZIP drops are moved.";
      };
      sapFailed = mkOption {
        type = types.str;
        default = "data/import/sap_import_failed";
        description = "Directory where failed SAP IS-H ZIP drops are moved.";
      };
      moverStaging = mkOption {
        type = types.str;
        default = "data/import/.move-my-files-staging";
        description = "Staging directory used by move-my-files before publishing watcher drops.";
      };
    };
  };
  managedEncryptedDataType = types.submodule {
    options = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Manage the lx-annotate encrypted data directory with a local LUKS-backed systemd unit.";
      };
      luksUuid = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "LUKS UUID opened by lx-annotate-encrypted-data.service.";
      };
      keyFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Key file used to unlock the encrypted data volume.";
      };
      luksUuidFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Optional file containing the LUKS UUID for the encrypted data volume.";
      };
      mapperName = mkOption {
        type = types.str;
        default = "lx-annotate-data";
        description = "Device-mapper name used for the unlocked encrypted data volume.";
      };
      fsType = mkOption {
        type = types.str;
        default = "ext4";
        description = "Filesystem type mounted for the encrypted lx-annotate data volume.";
      };
      mountOptions = mkOption {
        type = types.listOf types.str;
        default = [ "defaults" ];
        description = "Mount options passed to the encrypted data volume mount.";
      };
      owner = mkOption {
        type = types.str;
        default = "endoreg-service-user";
        description = "Owner applied to the mounted encrypted data directory.";
      };
      group = mkOption {
        type = types.str;
        default = "endoreg-service";
        description = "Group applied to the mounted encrypted data directory.";
      };
      dirMode = mkOption {
        type = types.str;
        default = "0750";
        description = "Permissions applied to the mounted encrypted data directory.";
      };
      after = mkOption {
        type = types.listOf types.str;
        default = [ "managed-secrets-setup.service" ];
        description = "Additional units ordered before the encrypted data service starts.";
      };
      requires = mkOption {
        type = types.listOf types.str;
        default = [ "managed-secrets-setup.service" ];
        description = "Additional units required by the encrypted data service.";
      };
    };
  };
  vaultManagedEncryptedDataType = types.submodule {
    options = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Fetch lx-annotate encrypted-data unlock material from Vault via managed-secrets.";
      };
      keyFilePath = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/lx_annotate_luks.key";
        description = "Local path where the Vault-backed LUKS key is written.";
      };
      luksUuidFilePath = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/lx_annotate_luks.uuid";
        description = "Local path where the Vault-backed LUKS UUID is written.";
      };
      masterKeyFilePath = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/lx_annotate_master_key";
        description = "Local path where the Vault-backed application master key is written.";
      };
      vaultPathTemplate = mkOption {
        type = types.str;
        default = "secret/data/nodes/{hostname}/lx-annotate";
        description = "Vault KV path template. {hostname} is replaced with networking.hostName.";
      };
      vaultKeyField = mkOption {
        type = types.str;
        default = "luks_key";
        description = "Field name in the Vault payload that contains the raw LUKS key material.";
      };
      vaultUuidField = mkOption {
        type = types.str;
        default = "luks_uuid";
        description = "Field name in the Vault payload that contains the LUKS UUID.";
      };
      vaultMasterKeyField = mkOption {
        type = types.str;
        default = "app_master_key";
        description = "Field name in the Vault payload that contains the application-layer master key.";
      };
      manageMasterKey = mkOption {
        type = types.bool;
        default = true;
        description = "Whether to provision the application master key from the same hostname-scoped Vault payload.";
      };
      setupService = mkOption {
        type = types.str;
        default = "managed-secrets-setup.service";
        description = "Systemd unit responsible for delivering the Vault-backed lx-annotate secret files.";
      };
    };
  };
  ffmpegStreamThrottleProfileType = types.submodule {
    options = {
      cpuQuota = mkOption {
        type = types.str;
        description = "Runtime CPUQuota applied to the FFmpeg worker in this stream-throttle profile.";
      };
      cpuWeight = mkOption {
        type = types.ints.between 1 10000;
        description = "Runtime CPUWeight applied to the FFmpeg worker in this stream-throttle profile.";
      };
      ioWeight = mkOption {
        type = types.ints.between 1 10000;
        description = "Runtime IOWeight applied to the FFmpeg worker in this stream-throttle profile.";
      };
    };
  };
  ffmpegStreamThrottleNormalProfileType = types.submodule {
    options = {
      cpuQuota = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Runtime CPUQuota applied when no user stream is active. Null follows runtime.workerPools.ffmpeg.cpuQuota.";
      };
      cpuWeight = mkOption {
        type = types.nullOr (types.ints.between 1 10000);
        default = null;
        description = "Runtime CPUWeight applied when no user stream is active. Null follows runtime.workerPools.ffmpeg.cpuWeight.";
      };
      ioWeight = mkOption {
        type = types.ints.between 1 10000;
        default = 100;
        description = "Runtime IOWeight applied when no user stream is active.";
      };
    };
  };
  ffmpegStreamThrottleType = types.submodule {
    options = {
      enable = mkOption {
        type = types.bool;
        default = true;
        description = "Enable runtime stream-aware throttling for the FFmpeg worker cgroup.";
      };
      interval = mkOption {
        type = types.str;
        default = "2m";
        description = "Systemd timer interval for reconciling stream-aware FFmpeg throttling.";
      };
      streaming = mkOption {
        type = ffmpegStreamThrottleProfileType;
        default = {
          cpuQuota = "50%";
          cpuWeight = 10;
          ioWeight = 10;
        };
        description = "Runtime cgroup profile applied while user stream leases are active.";
      };
      normal = mkOption {
        type = ffmpegStreamThrottleNormalProfileType;
        default = { };
        description = "Runtime cgroup profile applied after active stream leases expire.";
      };
    };
  };
  runtimeCommandsType = types.submodule {
    options = {
      web = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/lx-annotate-web";
        description = "Legacy wheel web command override.";
      };
      migrate = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django migrate --noinput --settings=lx_annotate.settings.settings_prod";
        description = "Legacy wheel migration command override.";
      };
      loadBaseData = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django load_base_db_data --settings=lx_annotate.settings.settings_prod";
        description = "Legacy wheel base-data command override.";
      };
      fileWatcher = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django run_filewatcher --settings=lx_annotate.settings.settings_prod";
        description = "Legacy wheel file watcher command override.";
      };
      fileWatcherOnce = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Legacy one-shot wheel file watcher command override.";
      };
      exportFrames = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/export-frames";
        description = "Legacy wheel frame export command override.";
      };
      celeryWorker = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/celery -A lx_annotate.celery:app worker --loglevel=INFO";
        description = "Legacy wheel Celery worker command override.";
      };
      sapImport = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django import_sap_ish_zip --settings=lx_annotate.settings.settings_prod";
        description = "Legacy wheel SAP import command override.";
      };
      mediaMigration = mkOption {
        type = types.nullOr types.str;
        default = "$LX_ANNOTATE_WHEEL_VENV/bin/python -m django migrate_media_storage --settings=lx_annotate.settings.settings_prod";
        description = "Legacy wheel media migration command override.";
      };
      transcodeVideo = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Legacy transcode command override.";
      };
    };
  };
  runtimeEnvironmentType = types.submodule {
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

  runtimeOptionGroups = {
    core = {
      mode = mkOption {
        type = types.enum [
          "repo"
          "wheel"
        ];
        default = "wheel";
        description = "Runtime artifact mode used by lx-annotate-local.";
      };

      deploymentRole = mkOption {
        type = types.nullOr (
          types.enum [
            "central_hub"
            "site_node"
            "standalone"
          ]
        );
        default = null;
        description = "Optional lx-annotate deployment role override. When null, the service derives the role from hub and central-node settings.";
      };

      encryptedDataDir = mkOption {
        type = types.str;
        default = "/var/lib/lx-annotate/data";
        description = "Canonical protected lx-annotate runtime data directory.";
      };

      intakeDirs = mkOption {
        type = runtimeIntakeDirsType;
        default = { };
        description = "Canonical lx-annotate intake directories.";
      };

      encryptionService = mkOption {
        type = types.nullOr types.str;
        default = null;
        description = "Optional systemd unit that unlocks or mounts the encrypted lx-annotate data directory.";
      };

      masterKeyFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Optional secret file exported as LX_ANNOTATE_MASTER_KEY_FILE for encrypted storage access.";
      };

      autoGenerateMasterKey = mkOption {
        type = types.bool;
        default = true;
        description = "Generate a per-machine application master key when no explicit runtime.masterKeyFile is configured.";
      };

      autoGeneratedMasterKeyFilePath = mkOption {
        type = types.path;
        default = "/etc/secrets/vault/lx_annotate_master_key";
        description = "Local path where the auto-generated per-machine application master key is written.";
      };

      managedEncryptedData = mkOption {
        type = managedEncryptedDataType;
        default = { };
        description = "Managed encrypted data mount configuration for lx-annotate.";
      };

      vaultManagedEncryptedData = mkOption {
        type = vaultManagedEncryptedDataType;
        default = { };
        description = "Hostname-aware Vault-backed provisioning for lx-annotate encrypted data secrets.";
      };
    };

    resources = {
      modelTrainingStagingRoot = mkOption {
        type = types.str;
        default = "/mnt/fast-nvme-cache/endoreg-training";
        description = "Ephemeral local staging root used by model-training jobs.";
      };

      tessdataPrefix = mkOption {
        type = types.str;
        default = "/run/current-system/sw/share/tessdata";
        description = "TESSDATA_PREFIX exported to wheel-based services.";
      };

      pytorchAllocConf = mkOption {
        type = types.str;
        default = "expandable_segments:True";
        description = "PYTORCH_ALLOC_CONF exported to wheel-based services.";
      };

      limits = mkOption {
        type = resourceLimitsType;
        default = { };
        description = "Systemd resource limits for the primary lx-annotate-local service.";
      };

      workerLimits = mkOption {
        type = workerLimitsType;
        default = { };
        description = "Systemd resource limits for the lx-annotate Celery worker.";
      };

      workerStartupDelaySec = mkOption {
        type = types.str;
        default = "90s";
        description = "Delay applied before always-on Celery workers start after lx-annotate boot.";
      };
    };

    workers = {
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
            ffmpeg = mkOption {
              type = workerPoolType;
              default = {
                concurrency = 1;
                maxTasksPerChild = 1;
                memoryHigh = "10G";
                memoryMax = "12G";
                cpuQuota = "600%";
                cpuWeight = 100;
                ioWeight = 100;
                nice = 0;
                oomScoreAdjust = 850;
              };
              description = "Celery pool for bounded FFmpeg media reprocessing.";
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
            llmInference = mkOption {
              type = workerPoolType;
              default = {
                concurrency = 1;
                maxTasksPerChild = 1;
                memoryHigh = "4G";
                memoryMax = "8G";
                cpuQuota = "150%";
                nice = 12;
                oomScoreAdjust = 350;
              };
              description = "Celery pool for Ollama-backed report and metadata LLM inference jobs.";
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

      ffmpegWorker = mkOption {
        type = ffmpegWorkerType;
        default = { };
        description = "Scheduling policy for the dedicated low-priority FFmpeg media Celery worker.";
      };

      ffmpegStreamThrottle = mkOption {
        type = ffmpegStreamThrottleType;
        default = { };
        description = "Stream-aware runtime throttling for the dedicated FFmpeg worker.";
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

      llmInferenceWorker = mkOption {
        type = llmInferenceWorkerType;
        default = { };
        description = "Scheduling policy for the dedicated Ollama-backed LLM inference Celery worker.";
      };
    };

    integrations = {
      externalServices = mkOption {
        type = externalServicesType;
        default = { };
        description = "External service endpoints for cluster-oriented lx-annotate deployments.";
      };

      celeryBroker = mkOption {
        type = celeryBrokerType;
        default = { };
        description = "Celery broker transport security controls.";
      };

      clustered = mkOption {
        type = clusteredType;
        default = { };
        description = "Cluster-readiness settings for lx-annotate.";
      };

      commands = mkOption {
        type = runtimeCommandsType;
        default = { };
        description = "Legacy wheel command overrides retained for compatibility.";
      };

      environment = mkOption {
        type = runtimeEnvironmentType;
        default = { };
        description = "Environment variable overrides for lx-annotate-local.";
      };
    };
  };
  runtimeOptions =
    runtimeOptionGroups.core
    // runtimeOptionGroups.resources
    // runtimeOptionGroups.workers
    // runtimeOptionGroups.integrations;

  mkEntrypoint =
    {
      cfg,
      endoregServiceUserHome,
      firstNonNull,
    }:
    let
      roleCfg = cfg.lxAnnotate;
      runtimeCfg = roleCfg.runtime;
      envDefaultsCfg = cfg.environmentDefaults;
      envOverrides = runtimeCfg.environment;

      defaultEnvironment = rec {
        hfHome = "${endoregServiceUserHome}/.cache/huggingface";
        hfHubCache = "${endoregServiceUserHome}/.cache/huggingface/hub";
        transformersCache = hfHubCache;
        ollamaModelsDir = "${endoregServiceUserHome}/.ollama/models";
      };

      environment = {
        hfHome = firstNonNull [
          envOverrides.hfHome
          envDefaultsCfg.hfHome
          defaultEnvironment.hfHome
        ];
        hfHubCache = firstNonNull [
          envOverrides.hfHubCache
          envDefaultsCfg.hfHubCache
          defaultEnvironment.hfHubCache
        ];
        transformersCache = firstNonNull [
          envOverrides.transformersCache
          envDefaultsCfg.transformersCache
          defaultEnvironment.transformersCache
        ];
        hfHubEnableTransfer =
          if envOverrides.hfHubEnableTransfer != null then
            envOverrides.hfHubEnableTransfer
          else
            envDefaultsCfg.hfHubEnableTransfer;
        ollamaModelsDir = firstNonNull [
          envOverrides.ollamaModelsDir
          envDefaultsCfg.ollamaModelsDir
          defaultEnvironment.ollamaModelsDir
        ];
        ollamaKeepAlive = firstNonNull [
          envOverrides.ollamaKeepAlive
          envDefaultsCfg.ollamaKeepAlive
        ];
      };

      djangoOverrides = {
        djangoModule = roleCfg.django.djangoModule;
        hostname = roleCfg.django.hostname;
        assetDir = if roleCfg.django.assetDir != null then roleCfg.django.assetDir else cfg.api.assetDir;
        port = 8117;
        djangoAllowedHosts = lib.unique (cfg.api.djangoAllowedHosts ++ [ roleCfg.django.hostname ]);
        keycloakClientId = "endoregdb-api";
      };

      djangoExtraSettings = lib.recursiveUpdate cfg.api.extraSettings (
        {
          CENTRAL_NODES = cfg.centralNodes;
          IS_CENTRAL_NODE = false;
        }
        // lib.optionalAttrs (cfg.defaultCenterKey != null) {
          DEFAULT_CENTER_KEY = cfg.defaultCenterKey;
        }
      );

      django = lib.recursiveUpdate cfg.api (
        djangoOverrides
        // {
          extraSettings = djangoExtraSettings;
        }
      );
      serviceDjango = (lib.mapAttrs (_: value: lib.mkDefault value) django) // {
        extraSettings = lib.mapAttrs (_: value: lib.mkDefault value) djangoExtraSettings;
        port = lib.mkForce 8117;
      };

      serviceRuntime = {
        mode = lib.mkDefault runtimeCfg.mode;
        deploymentRole = lib.mkIf (runtimeCfg.deploymentRole != null) (
          lib.mkDefault runtimeCfg.deploymentRole
        );
        encryptedDataDir = lib.mkDefault runtimeCfg.encryptedDataDir;
        intakeDirs = lib.mkDefault runtimeCfg.intakeDirs;
        encryptionService = lib.mkIf (runtimeCfg.encryptionService != null) (
          lib.mkDefault runtimeCfg.encryptionService
        );
        masterKeyFile = lib.mkIf (runtimeCfg.masterKeyFile != null) (
          lib.mkDefault runtimeCfg.masterKeyFile
        );
        autoGenerateMasterKey = lib.mkDefault runtimeCfg.autoGenerateMasterKey;
        autoGeneratedMasterKeyFilePath = lib.mkDefault runtimeCfg.autoGeneratedMasterKeyFilePath;
        managedEncryptedData = lib.mkDefault runtimeCfg.managedEncryptedData;
        vaultManagedEncryptedData = lib.mkDefault runtimeCfg.vaultManagedEncryptedData;
        tessdataPrefix = lib.mkDefault runtimeCfg.tessdataPrefix;
        pytorchAllocConf = lib.mkDefault runtimeCfg.pytorchAllocConf;
        modelTrainingStagingRoot = lib.mkDefault runtimeCfg.modelTrainingStagingRoot;
        limits = lib.mkDefault runtimeCfg.limits;
        workerLimits = lib.mkDefault runtimeCfg.workerLimits;
        workerStartupDelaySec = lib.mkDefault runtimeCfg.workerStartupDelaySec;
        workerPools = lib.mkDefault runtimeCfg.workerPools;
        frameExtractionWorker = lib.mkDefault runtimeCfg.frameExtractionWorker;
        ffmpegWorker = lib.mkDefault runtimeCfg.ffmpegWorker;
        ffmpegStreamThrottle = lib.mkDefault runtimeCfg.ffmpegStreamThrottle;
        inferenceWorker = lib.mkDefault runtimeCfg.inferenceWorker;
        trainingWorker = lib.mkDefault runtimeCfg.trainingWorker;
        llmInferenceWorker = lib.mkDefault runtimeCfg.llmInferenceWorker;
        externalServices = lib.mkDefault runtimeCfg.externalServices;
        celeryBroker = {
          requireSecureTransport = lib.mkIf runtimeCfg.celeryBroker.requireSecureTransport (
            lib.mkDefault true
          );
          secureTransportConfirmed = lib.mkIf runtimeCfg.celeryBroker.secureTransportConfirmed (
            lib.mkDefault true
          );
        };
        clustered = lib.mkDefault runtimeCfg.clustered;
        commands = lib.mkDefault runtimeCfg.commands;
      };
    in
    {
      enable = roleCfg.enable;
      environment = {
        values = environment;
        extraEnv = {
          HF_HOME = environment.hfHome;
          HF_HUB_CACHE = environment.hfHubCache;
          TRANSFORMERS_CACHE = environment.transformersCache;
          OLLAMA_MODELS = environment.ollamaModelsDir;
          HF_HUB_ENABLE_HF_TRANSFER = if environment.hfHubEnableTransfer then "1" else "0";
        }
        // lib.optionalAttrs (environment.ollamaKeepAlive != null) {
          OLLAMA_KEEP_ALIVE = environment.ollamaKeepAlive;
        };
      };
      service = {
        enable = roleCfg.enable;
        debug.enable = roleCfg.debug.enable;
        source = roleCfg.source;
        django = serviceDjango;
        database = cfg.database;
        runtime = serviceRuntime;
      };
    };
in
{
  options = {
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
          hostname = mkOption {
            type = types.str;
            default = "lx-annotate.local";
            description = "Public DNS hostname used by LX-Annotate, Nginx, and its TLS certificate.";
          };

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
        options = runtimeOptions;
      };
      default = { };
      description = "Runtime configuration for lx-annotate-local.";
    };
  };

  entrypoint = mkEntrypoint;
}
