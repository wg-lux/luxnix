{
  config,
  lib,
  pkgs,
  cfg,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (builtins) elemAt;
  inherit (lib) literalExpression mkOption types;
  inherit (lib.luxnix) mkBoolOpt;

  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-group-name
    ;
  inherit (runtime.helpers) mkDjangoOptions;
  inherit (runtime.defaults)
    externalCleanupArchiveRootDefault
    emergencyReliefArchiveRootDefault
    emergencyReliefManifestDirDefault
    emergencyReliefStagingDirDefault
    emergencyReliefValidatedExportDirsDefault
    ;
  inherit (runtime.paths)
    runtimeDataRootPath
    dataRecoveryStateFile
    hubBackupIncomingPath
    hubBackupSnapshotPath
    hubBackupManifestPath
    legacyRepoDataRootPath
    legacyRepoMediaRootPath
    legacyDataProcessedReportDir
    legacyDataProcessedVideoDir
    legacyMediaProcessedReportDir
    legacyMediaProcessedVideoDir
    runtimeProcessedReportDir
    runtimeProcessedVideoDir
    ;
  inferWheelPackageVersion =
    wheelPath:
    if wheelPath == null then
      ""
    else
      let
        wheelFileName = builtins.baseNameOf (toString wheelPath);
        versionMatch = builtins.match ".*lx_annotate-([^-]+)-.*[.]whl" wheelFileName;
      in
      if versionMatch == null then "" else elemAt versionMatch 0;
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
        default = "maintenance-window";
        description = "Scheduling mode for export-stage frame extraction. Maintenance-window keeps bounded frame materialization out of foreground hours by default.";
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
  runtimeIntakeDirsType = types.submodule {
    options = {
      importRoot = mkOption {
        type = types.str;
        default = "data/import";
        description = "Runtime intake root. Relative values are resolved below runtime.encryptedDataDir; secretspec-style data/... values are resolved by replacing the leading data segment.";
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
        description = "Staging directory used by move-my-files before publishing drops into watcher intake directories.";
      };
    };
  };
in
{
  options.services.luxnix.lxAnnotateLocal = {
    enable = mkBoolOpt false "Enable LxAnnotate Service";

    # Debug configuration
    debug = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Enable verbose debug output including sensitive file information. Should be disabled in production.";
          };
        };
      };
      default = { };
      description = "Debug configuration for lx-annotate-local.";
    };

    # Source/Repository configuration
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

    runtime = mkOption {
      type = types.submodule {
        options = {
          mode = mkOption {
            type = types.enum [
              "repo"
              "wheel"
            ];
            default = "wheel";
            description = ''
              Runtime artifact mode. wheel installs runtime.wheelPath into a
              host-local virtualenv and exposes the wheel console scripts as the
              effective runtime package used by services.lx-annotate and the
              LuxNix helper units. repo uses runtime.package directly.
            '';
          };
          package = mkOption {
            type = types.package;
            default = pkgs.lx-annotate;
            defaultText = literalExpression "pkgs.lx-annotate";
            description = "Packaged lx-annotate derivation used when runtime.mode = \"repo\".";
          };
          deploymentRole = mkOption {
            type = types.enum [
              "central_hub"
              "site_node"
              "standalone"
            ];
            default = "site_node";
            description = ''
              Explicit endoreg_db deployment role exported as ENDOREG_DEPLOYMENT_ROLE.
              LuxNix central server nodes map to central_hub. LuxNix laptop
              center nodes map to the lx-annotate/endoreg_db site_node value.
              Use standalone only for isolated, non-networked test deployments.
            '';
          };
          wheelPath = mkOption {
            type = types.nullOr types.path;
            default = pkgs.fetchurl {
              url = "https://files.pythonhosted.org/packages/93/62/e24697ffeee115a56527603821f2b77df08fbf39d4f303880c95306536e6/lx_annotate-0.7.5-py3-none-any.whl";
              hash = "sha256-xLTSY82/J63Mj6gzg5h5DVVlwDjWm8e3kWvgVXVjljY=";
            };
            description = "Path to the lx-annotate wheel artifact used in wheel mode.";
          };
          packageVersion = mkOption {
            type = types.str;
            default = inferWheelPackageVersion cfg.runtime.wheelPath;
            defaultText = literalExpression "version parsed from runtime.wheelPath";
            description = "lx-annotate Python package version exported as LX_ANNOTATE_PACKAGE_VERSION.";
          };
          wheelhousePath = mkOption {
            type = types.nullOr types.path;
            default = null;
            example = "/var/lib/lx-annotate/artifacts/wheelhouse";
            description = "Optional directory containing prebuilt dependency wheels. When set, wheel installs run with --no-index --find-links so the service does not resolve/download dependencies from the network during startup.";
          };
          encryptedDataDir = mkOption {
            type = types.str;
            default = "/var/lib/lx-annotate/data";
            description = "External encrypted runtime data directory. Must stay outside the repo/app path.";
          };
          intakeDirs = mkOption {
            type = runtimeIntakeDirsType;
            default = { };
            description = "Canonical lx-annotate intake directories. Defaults mirror lx-annotate secretspec.toml watcher path defaults.";
          };
          encryptionService = mkOption {
            type = types.nullOr types.str;
            default = null;
            example = "lx-annotate-encrypted-data.service";
            description = "Optional systemd unit that unlocks or mounts the encrypted lx-annotate data directory before app services start.";
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
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Manage / unlock the lx-annotate encrypted data directory with a local LUKS-backed systemd unit.";
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
                  default = endoreg-service-user-name;
                  description = "Owner applied to the mounted encrypted data directory.";
                };
                group = mkOption {
                  type = types.str;
                  default = endoreg-service-group-name;
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
            default = { };
            description = "Managed encrypted data mount configuration for lx-annotate.";
          };
          vaultManagedEncryptedData = mkOption {
            type = types.submodule {
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
                  description = "Vault KV path template. `{hostname}` is replaced with networking.hostName.";
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
            default = { };
            description = "Hostname-aware Vault-backed provisioning for lx-annotate encrypted data secrets.";
          };
          pythonPackage = mkOption {
            type = types.package;
            default = pkgs.python312;
            description = "Python interpreter used to create the runtime virtualenv in wheel mode.";
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
          modelTrainingStagingRoot = mkOption {
            type = types.str;
            default = "/mnt/fast-nvme-cache/endoreg-training";
            description = "Ephemeral local staging root used by model-training jobs.";
          };
          limits = mkOption {
            type = types.submodule {
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
            default = { };
            description = "Systemd resource limits for the primary lx-annotate-local service.";
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
            description = "Systemd resource limits for the lx-annotate Celery worker.";
          };
          workerStartupDelaySec = mkOption {
            type = types.str;
            default = "90s";
            description = "Delay applied before always-on Celery workers start after lx-annotate boot.";
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
                ffmpeg = mkOption {
                  type = workerPoolType;
                  default = {
                    concurrency = 1;
                    maxTasksPerChild = 1;
                    memoryHigh = "10G";
                    memoryMax = "12G";
                    cpuQuota = "200%";
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
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = true;
                  description = "Enable runtime stream-aware throttling for the FFmpeg worker cgroup.";
                };
                interval = mkOption {
                  type = types.str;
                  default = "10s";
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
          externalServices = mkOption {
            type = types.submodule {
              options = {
                redisUrl = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  example = "rediss://redis.lx-annotate.svc.cluster.local:6379/1";
                  description = "Optional external Redis/Celery broker URL. Defaults to the local endoreg-client CELERY_BROKER_URL contract when unset.";
                };
                postgresHost = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  example = "postgres.lx-annotate.svc.cluster.local";
                  description = "Optional external PostgreSQL host used for clustered lx-annotate deployments.";
                };
                postgresPort = mkOption {
                  type = types.nullOr types.port;
                  default = null;
                  example = 5432;
                  description = "Optional external PostgreSQL port used with runtime.externalServices.postgresHost.";
                };
              };
            };
            default = { };
            description = "Explicit external service endpoints for cluster-oriented lx-annotate deployments.";
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
                  description = "Enable fail-closed checks for cluster-oriented lx-annotate deployment contracts.";
                };
                sharedStorage = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Operator acknowledgement that runtime.encryptedDataDir is backed by shared cluster storage.";
                };
                sharedMasterKeyFile = mkOption {
                  type = types.nullOr types.path;
                  default = null;
                  example = "/run/secrets/lx-annotate/master-key";
                  description = "Shared workload master key file for clustered lx-annotate pods/workers.";
                };
              };
            };
            default = { };
            description = "Cluster-readiness guardrails for lx-annotate.";
          };
          commands = mkOption {
            type = types.submodule {
              options = {
                web = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-web console script.";
                };
                migrate = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-migrate console script.";
                };
                loadBaseData = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-load-base-data console script.";
                };
                fileWatcher = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-watch console script.";
                };
                fileWatcherOnce = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override for one-shot watcher runs.";
                };
                exportFrames = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-export-frames console script.";
                };
                celeryWorker = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-worker console script.";
                };
                sapImport = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. Wheel mode normally uses the lx-annotate-import-sap console script.";
                };
                mediaMigration = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override for media migration helper scripts.";
                };
                transcodeVideo = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  description = "Legacy helper override. The active file mover adapter uses lx-annotate-manage directly.";
                };
              };
            };
            default = { };
            description = "Additional service commands used in wheel mode.";
          };
        };
      };
      default = { };
      description = "Runtime bootstrap configuration for lx-annotate.";
    };

    # Django configuration (passed from endoreg-client role)
    django = mkOption {
      type = types.submodule {
        options = mkDjangoOptions {
          defaults = {
            hostname = "lx-annotate.local";
            port = 8117;
            useHttps = false;
            sslCertificatePath = null;
            sslKeyPath = null;
            djangoAllowedHosts = [
              "lx-annotate.local"
              "127.0.0.1"
            ];
            corsAllowedOrigins = [
              "https://lx-annotate.local"
              "http://127.0.0.1"
            ];
            djangoDebug = false;
            djangoSecretKeyFile = "/etc/secrets/vault/django_secret_key";
            keycloakSecretFile = "/etc/secrets/vault/keycloak.env";
            keycloakClientId = "endoregdb-api";
            logLevel = "INFO";
            maxRequestSize = "100M";
            timeZone = "Europe/Berlin";
            language = "en-us";
            settingsProfile = "prod";
            settingsModule = null;
            djangoEnv = null;
            dataDir = "data";
            confDir = "conf";
            confTemplateDir = "conf_template";
            djangoModule = "lx_annotate";
            assetDir = "tests/assets";
            httpProtocol = "http";
            baseUrl = null;
            staticUrl = "/static/";
            mediaUrl = "/media/";
            runVideoTests = false;
            skipExpensiveTests = true;
            extraSettings = { };
          };
          includeKeycloak = true;
          logLevelType = types.str;
          httpProtocolType = types.str;
        };
      };
      default = { };
      description = "Django configuration options for lx-annotate.";
    };

    # Database configuration
    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption {
            type = types.str;
            default = "lx-annotate.local";
          };
          port = mkOption {
            type = types.port;
            default = 5433;
          };
          name = mkOption {
            type = types.str;
            default = "lxAnnotateLocal";
          };
          user = mkOption {
            type = types.str;
            default = "lxAnnotateLocal";
          };
          passwordFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
          };
          sslMode = mkOption {
            type = types.str;
            default = "prefer";
          };
          endoregLocalUserPasswordFile = mkOption {
            type = types.path;
            default = "/var/lib/postgresql/endoregDbLocal.password";
            description = "Path to file containing endoregDbLocal user password";
          };
        };
      };
      default = { };
      description = "Database configuration options";
    };

    dataRecovery = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = true;
            description = "Recover legacy lx-annotate data and media trees into the runtime STORAGE_DIR before boot.";
          };
          legacyDataDir = mkOption {
            type = types.str;
            default = legacyRepoDataRootPath;
            description = "Legacy repo-local data directory to sync from.";
          };
          legacyMediaDir = mkOption {
            type = types.str;
            default = legacyRepoMediaRootPath;
            description = "Legacy media directory to sync from.";
          };
          stateFile = mkOption {
            type = types.str;
            default = dataRecoveryStateFile;
            description = "Stable state file that records the last effective lx-annotate data directory used for migration drift detection.";
          };
        };
      };
      default = { };
      description = "Recovery settings for migrating legacy lx-annotate media into the runtime storage root.";
    };

    streamableMigration = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Expose the manual lx-annotate video streamable backfill systemd unit. The unit is not started by any target.";
          };
        };
      };
      default = { };
      description = "Settings for the manual streamable video backfill migration unit.";
    };

    dataCleanup = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = config.roles.endoreg-client.paths.storagePersistingEnable;
            description = "Regularly move duplicate anonymized lx-annotate payload into external archive storage.";
          };
          legacyDataDir = mkOption {
            type = types.str;
            default = legacyRepoDataRootPath;
            description = "Legacy repo-local data directory to clean up.";
          };
          legacyMediaDir = mkOption {
            type = types.str;
            default = legacyRepoMediaRootPath;
            description = "Legacy media directory to clean up.";
          };
          legacyProcessedReportDir = mkOption {
            type = types.str;
            default = legacyDataProcessedReportDir;
            description = "Legacy processed report directory derived from the lx-annotate service paths.";
          };
          legacyProcessedVideoDir = mkOption {
            type = types.str;
            default = legacyDataProcessedVideoDir;
            description = "Legacy processed video directory derived from the lx-annotate service paths.";
          };
          legacyMediaProcessedReportDir = mkOption {
            type = types.str;
            default = legacyMediaProcessedReportDir;
            description = "Legacy processed report directory under the service media root.";
          };
          legacyMediaProcessedVideoDir = mkOption {
            type = types.str;
            default = legacyMediaProcessedVideoDir;
            description = "Legacy processed video directory under the service media root.";
          };
          archiveDir = mkOption {
            type = types.str;
            default = externalCleanupArchiveRootDefault;
            description = "External archive directory where duplicate files are moved.";
          };
          runtimeProcessedReportDir = mkOption {
            type = types.str;
            default = runtimeProcessedReportDir;
            description = "Runtime processed report directory derived from the lx-annotate service.";
          };
          runtimeProcessedVideoDir = mkOption {
            type = types.str;
            default = runtimeProcessedVideoDir;
            description = "Runtime processed video directory derived from the lx-annotate service.";
          };
          onCalendar = mkOption {
            type = types.str;
            default = "daily";
            description = "systemd timer schedule for duplicate cleanup.";
          };
        };
      };
      default = { };
      description = "Duplicate cleanup settings for anonymized lx-annotate legacy storage.";
    };

    storageRelief = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Expose the manual emergency storage relief service. The service only archives verified anonymized duplicate payloads and explicitly validated export bundles.";
          };
          dryRun = mkOption {
            type = types.bool;
            default = false;
            description = "Report what emergency storage relief would archive without copying or deleting files.";
          };
          deleteAfterVerify = mkOption {
            type = types.bool;
            default = true;
            description = "Delete local source files only after the external archive copy has been hash-verified.";
          };
          requireExternalMount = mkOption {
            type = types.bool;
            default = true;
            description = "Fail closed unless the external persisting storage mount is active and matches the configured device id or filesystem UUID.";
          };
          externalMountPoint = mkOption {
            type = types.str;
            default = toString config.roles.endoreg-client.paths.storagePersistingMountPoint;
            description = "External mount point used for emergency relief archives.";
          };
          expectedDeviceId = mkOption {
            type = types.nullOr types.str;
            default =
              let
                value = lib.attrByPath [ "secretspec" "secrets" "STORAGE_PERSISTING_HDD_ID" ] "" config;
              in
              if value == "" then null else value;
            description = "Expected /dev/disk/by-id basename for the external relief volume. Required when expectedFsUuid is unset.";
          };
          expectedDevicePart = mkOption {
            type = types.str;
            default = lib.attrByPath [ "secretspec" "secrets" "STORAGE_PERSISTING_HDD_PART" ] "part1" config;
            description = "Partition suffix appended to expectedDeviceId when checking the mounted device.";
          };
          expectedFsUuid = mkOption {
            type = types.nullOr types.str;
            default = null;
            description = "Optional filesystem UUID accepted for the external relief volume. Use this when the mounted source is a mapper device rather than a plain by-id partition.";
          };
          archiveDir = mkOption {
            type = types.str;
            default = emergencyReliefArchiveRootDefault;
            description = "External archive root for emergency storage relief output.";
          };
          manifestDir = mkOption {
            type = types.str;
            default = emergencyReliefManifestDirDefault;
            description = "External directory where emergency relief JSON manifests are written.";
          };
          stagingDir = mkOption {
            type = types.str;
            default = emergencyReliefStagingDirDefault;
            description = "External staging directory used while emergency relief copies are being verified.";
          };
          includeLegacyProcessedDuplicates = mkOption {
            type = types.bool;
            default = true;
            description = "Archive legacy processed report/video duplicates only when the matching database object is anonymization-export eligible and content hashes match.";
          };
          includeValidatedExportBundles = mkOption {
            type = types.bool;
            default = true;
            description = "Archive export bundles only when they contain a validation marker referencing eligible database resources.";
          };
          validatedExportDirs = mkOption {
            type = types.listOf types.str;
            default = emergencyReliefValidatedExportDirsDefault;
            description = "Directories scanned for validated export bundle marker files.";
          };
          validatedExportMarkerNames = mkOption {
            type = types.listOf types.str;
            default = [ ".lx-annotate-export-validated.json" ];
            description = "Marker filenames that make an export bundle eligible for emergency relief. Marker files must contain JSON with validated=true and eligible resource references.";
          };
          timer = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Run emergency storage relief on a timer. Disabled by default; manual starts are preferred for emergency use.";
                };
                onCalendar = mkOption {
                  type = types.str;
                  default = "hourly";
                  description = "systemd OnCalendar schedule for the emergency relief timer when enabled.";
                };
              };
            };
            default = { };
            description = "Optional timer for emergency storage relief.";
          };
        };
      };
      default = { };
      description = "Emergency storage pressure relief settings for lx-annotate.";
    };

    hub = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = config.networking.hostName == "gs-02";
            description = "Mark this host as the central lx-annotate hub node and enable central-node groundwork defaults.";
          };
          transferApi = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Enable the authenticated node-to-node hub transfer API. Disabled by default even on hub nodes.";
                };
                requireSecureTransport = mkOption {
                  type = types.bool;
                  default = true;
                  description = "Require HTTPS-equivalent secure transport for hub transfer requests.";
                };
                requireMtls = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Require proxy-verified mutual TLS for node-authenticated hub transfer requests.";
                };
                mtlsMetaKey = mkOption {
                  type = types.str;
                  default = "HTTP_X_CLIENT_CERT_VERIFIED";
                  description = "Django request META key used to verify proxy-attested mTLS client authentication.";
                };
                mtlsMetaValue = mkOption {
                  type = types.str;
                  default = "SUCCESS";
                  description = "Expected proxy-attested mTLS verification value forwarded to Django.";
                };
                clientCaFile = mkOption {
                  type = types.nullOr (types.either types.path types.str);
                  default = null;
                  description = "PEM bundle used by Nginx to verify client certificates for hub transfer requests.";
                };
              };
            };
            default = { };
            description = "Transfer API settings for lx-annotate hub deployments.";
          };
          backup = mkOption {
            type = types.submodule {
              options = {
                enable = mkOption {
                  type = types.bool;
                  default = false;
                  description = "Enable protected backup groundwork on the hub node. This provisions a landing area for inbound backups and periodic local runtime snapshots.";
                };
                incomingDir = mkOption {
                  type = types.str;
                  default = hubBackupIncomingPath;
                  description = "Protected landing directory for inbound backups staged on the hub node.";
                };
                snapshotDir = mkOption {
                  type = types.str;
                  default = hubBackupSnapshotPath;
                  description = "Protected directory where the hub node stores timestamped runtime snapshots.";
                };
                manifestDir = mkOption {
                  type = types.str;
                  default = hubBackupManifestPath;
                  description = "Protected directory for JSON manifests describing generated hub snapshots.";
                };
                sourceRuntimeDir = mkOption {
                  type = types.str;
                  default = runtimeDataRootPath;
                  description = "Runtime tree snapshotted by the hub backup service. This should remain the encrypted lx-annotate data root.";
                };
                onCalendar = mkOption {
                  type = types.str;
                  default = "hourly";
                  description = "systemd timer schedule for hub runtime snapshots.";
                };
                retainCount = mkOption {
                  type = types.int;
                  default = 48;
                  description = "How many completed snapshots the hub node keeps before pruning older ones.";
                };
                exclude = mkOption {
                  type = types.listOf types.str;
                  default = [
                    ".lx-annotate-rsync-partial"
                    "temp"
                    "frames"
                    "raw_frames"
                    "hub/backup/incoming"
                    "hub/backup/snapshots"
                    "hub/backup/manifests"
                  ];
                  description = "Paths excluded from hub runtime snapshots. Defaults omit disposable frame/temp output and the backup directories themselves.";
                };
              };
            };
            default = { };
            description = "Central hub backup groundwork settings.";
          };
        };
      };
      default = { };
      description = "Central hub groundwork settings for lx-annotate.";
    };
  };
}
