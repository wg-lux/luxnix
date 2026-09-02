{
  lib,
  pkgs,
  cfg,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (builtins) elemAt;
  inherit (lib) literalExpression mkOption types;
  runtime = lxAnnotateRuntime;
  inherit (runtime.identities)
    endoreg-service-user-name
    endoreg-service-group-name
    ;
  inherit (runtime.paths)
    runtimeDataRootPath
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
      timeoutStopSec = mkOption {
        type = types.str;
        default = "6h15min";
        description = "Warm-shutdown grace period for an active FFmpeg media task before systemd may send a final kill signal.";
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
    };
  };
in
{
  options.services.luxnix.lxAnnotateLocal = {
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
              url = "https://files.pythonhosted.org/packages/f0/91/8a662b5ad67b3ae87a30a3bba27d6c12d83c8e0d096d3515501757622ebe/lx_annotate-1.2.0-py3-none-any.whl";
              hash = "sha256-K94F5oUwxEnBPLHpfZEOYORX6CwoQXm1VD7FjoQdhI8=";
            };
            description = "Path to the lx-annotate wheel artifact used in wheel mode.";
          };
          packageVersion = mkOption {
            type = types.str;
            default = inferWheelPackageVersion cfg.runtime.wheelPath;
            defaultText = literalExpression "version parsed from runtime.wheelPath";
            description = "lx-annotate Python package version exported as LX_ANNOTATE_PACKAGE_VERSION.";
          };
          extraEnvironment = mkOption {
            type = types.attrsOf types.str;
            default = { };
            example = {
              SERVE_WITH_NGINX = "true";
              LOG_LEVEL = "INFO";
            };
            description = "Additional lx-annotate environment variables merged into the generated systemd environment. Use this for secretspec keys that do not need a dedicated LuxNix option.";
          };
          wheelhousePath = mkOption {
            type = types.nullOr types.path;
            default = null;
            example = "/var/lib/lx-annotate/artifacts/wheelhouse";
            description = "Optional directory containing prebuilt dependency wheels. When set, wheel installs run with --no-index --find-links so the service does not resolve/download dependencies from the network during startup.";
          };
          wheelDependencyOverrides = mkOption {
            type = types.listOf types.str;
            default = [ ];
            description = ''
              Python packages force-upgraded with --no-deps after installing
              the lx-annotate wheel. This carries targeted runtime fixes while
              the upstream lx-annotate wheel still pins an older transitive
              dependency. If runtime.wheelhousePath is set, matching wheels must
              be present in that wheelhouse.
            '';
          };
          terminology = mkOption {
            type = types.submodule {
              options = {
                registryPath = mkOption {
                  type = types.str;
                  default = "${runtimeDataRootPath}/terminology/registry.json";
                  description = ''
                    Writable governed lx-dtypes knowledge-base registry. The
                    path must remain inside runtime.encryptedDataDir.
                  '';
                };
                importRoot = mkOption {
                  type = types.str;
                  default = "${runtimeDataRootPath}/terminology/packages";
                  description = ''
                    Writable root for validated terminology bundle imports. The
                    path must remain inside runtime.encryptedDataDir.
                  '';
                };
                initialBundle = mkOption {
                  type = types.nullOr (
                    types.submodule {
                      options = {
                        inputDirectory = mkOption {
                          type = types.path;
                          description = ''
                            Immutable parent directory containing the initial
                            knowledge-base module. Nix retains this path in the
                            deployment closure.
                          '';
                        };
                        moduleName = mkOption {
                          type = types.str;
                          description = "Declared module name from the bundle config.yaml.";
                        };
                        version = mkOption {
                          type = types.str;
                          description = "Declared module version from the bundle config.yaml.";
                        };
                        medicalField = mkOption {
                          type = types.nullOr types.str;
                          default = null;
                          description = "Optional medical-field metadata stored with the registry entry.";
                        };
                      };
                    }
                  );
                  default = null;
                  description = ''
                    Optional immutable bundle used only when no registry exists.
                    When this is null, the bootstrap registers the packaged
                    dgvs_reporting, mst_3_0, and star_upper_gi reporting bundles
                    and activates star_upper_gi in a new registry. Provisioning failures only
                    disable terminology features; they do not block LX-Annotate.
                    An authorized user can also import a data folder or an
                    lx-terminology-editor ZIP from the frontend.
                    Existing registries and later operator selections are never
                    reset.
                  '';
                };
              };
            };
            default = { };
            description = "Governed lx-dtypes terminology registry configuration.";
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
          streamableServing = mkOption {
            type = types.submodule {
              options = {
                nginxOffload = mkOption {
                  type = types.bool;
                  default = true;
                  description = "Export SERVE_WITH_NGINX for lx-annotate stream endpoints so authenticated video responses use Nginx X-Accel-Redirect instead of app-level byte streaming.";
                };
                protectedMediaUrl = mkOption {
                  type = types.str;
                  default = "/protected_media/";
                  description = "Internal Nginx location prefix exported as NGINX_PROTECTED_MEDIA_URL for protected lx-annotate media offload.";
                };
                externalStorageRoot = mkOption {
                  type = types.nullOr types.str;
                  default = null;
                  example = "/data/raid01/lx-annotate/streamable_videos";
                  description = ''
                    Optional external filesystem root for streamable video artifacts.
                    When set, LuxNix bind-mounts this directory onto the canonical
                    protected-media streamable subtree below runtime.encryptedDataDir.
                    The lx-annotate application and nginx continue to use
                    runtime.encryptedDataDir/storage/streamable_videos so persisted
                    streamable relative paths remain stable.
                  '';
                };
              };
            };
            default = { };
            description = "Nginx-backed protected media serving controls for lx-annotate streamable video artifacts.";
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
                hubTransfer = mkOption {
                  type = workerPoolType;
                  default = {
                    concurrency = 1;
                    maxTasksPerChild = 20;
                    memoryHigh = "768M";
                    memoryMax = "1536M";
                    cpuQuota = "35%";
                    nice = 14;
                    oomScoreAdjust = 750;
                  };
                  description = "Celery pool dedicated to bounded outbound hub transfer and recovery jobs.";
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
                  description = "Legacy helper override retained for older media migration helper scripts. The streamable migration unit uses lx-annotate-manage directly.";
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
  };
}
