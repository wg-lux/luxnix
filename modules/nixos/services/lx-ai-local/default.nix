{ config
, lib
, pkgs
, ...
}:
with lib;
with lib.luxnix;

let
  cfg = config.services.luxnix.lxAiLocal;

  scriptName = "runLxAiTraining";

  gitURL = cfg.source.url;
  repoDirName = "lx-ai";
  branchName = cfg.source.branch;

  endoreg-service-user-name = config.user.endoreg-service-user.name;
  endoreg-service-user = config.users.users.${endoreg-service-user-name};
  endoreg-service-user-home = endoreg-service-user.home;
  endoreg-service-group-name = config.user.endoreg-service-user.group;

  repoDir = "${endoreg-service-user-home}/${repoDirName}";

  makeRuntimePath = path:
    if lib.hasPrefix "/" path then path else "${repoDir}/${path}";

  # lx-ai owned runtime/output root.
  #
  # Current default behavior remains unchanged:
  #   cfg.runtime.dataDir = "data"
  #   envDataDir          = /var/endoreg-service-user/lx-ai/data
  #
  # Later this can safely become:
  #   cfg.runtime.dataDir = "/var/lib/lx-ai/data"
  # without changing Python code.
  envDataDir = makeRuntimePath cfg.runtime.dataDir;

  # Protected media root used by endoreg-db path resolution.
  #
  # Default:
  #   envProtectedDataDir = envDataDir
  #
  # Future lx-annotate shared-media mode:
  #   cfg.runtime.protectedDataDir = "/var/lib/lx-annotate/data"
  #
  # Then lx-ai writes frames to envDataDir, but reads protected videos from
  # envProtectedDataDir/storage through endoreg-db.
  envProtectedDataDir =
    if cfg.runtime.protectedDataDir != null
    then makeRuntimePath cfg.runtime.protectedDataDir
    else envDataDir;

  envConfDir = makeRuntimePath cfg.runtime.confDir;

  envFrameDir = "${envDataDir}/frames";
  envFrameMaterializationOutputRoot = "${envFrameDir}/generated";

  envTrainingRoot = "${envDataDir}/model_training";
  envCheckpointsDir = "${envTrainingRoot}/checkpoints";
  envRunsDir = "${envTrainingRoot}/runs";
  envBucketSnapshotDir = "${envTrainingRoot}/buckets";
  envBackboneCheckpoint = "${envCheckpointsDir}/RN50_GastroNet-1M_DINOv1.pth";
  envBackboneCheckpointUrl = cfg.runtime.backboneCheckpointUrl;

  envCsvDir = "${envDataDir}/import/csv";
  envLegacyImageDir = "${envDataDir}/legacy_images/images";
  envLegacyJsonlPath = "${envDataDir}/legacy_images/legacy_img_dicts.jsonl";

  # Canonical protected-media layout matching endoreg_db.utils.paths:
  #
  # LX_ANNOTATE_ENCRYPTED_DATA_DIR = envProtectedDataDir
  # STORAGE_DIR                    = envProtectedDataDir/storage
  # PROTECTED_MEDIA_ROOT           = envProtectedDataDir/storage
  #
  # VideoFile.processed_file values like:
  #   processed_videos_final/<hash>.mp4
  #
  # resolve under:
  #   ${envStorageDir}/processed_videos_final/<hash>.mp4
  envStorageDir = "${envProtectedDataDir}/storage";
  envProcessedVideoDir = "${envStorageDir}/processed_videos_final";

  envPlaintextTmpDir = "${envDataDir}/temp/plaintext_media";

  envStreamableVideoRoot = "${envStorageDir}/streamable_videos";
  envStreamableVideoRawRoot = "${envStreamableVideoRoot}/raw";
  envStreamableVideoProcessedRoot = "${envStreamableVideoRoot}/processed";

  envSystemdFilePath = "${repoDir}/.env.systemd";

  encryptionServiceUnits =
    lib.optionals (cfg.runtime.encryptionService != null) [
      cfg.runtime.encryptionService
    ];

  runLxAiTraining = pkgs.writeShellScriptBin "${scriptName}" ''
    set -euo pipefail

    DEBUG_MODE=${if cfg.debug.enable then "true" else "false"}
    if [ "$DEBUG_MODE" = "true" ]; then
      set -x
    fi

    echo "Starting LxAI service..."
    echo "Repository: ${gitURL}"
    echo "Branch: ${branchName}"

    if [ -d "${repoDir}" ] && [ ! -d "${repoDir}/.git" ]; then
      echo "WARNING: ${repoDir} exists but is not a git repository. Removing it."
      rm -rf "${repoDir}"
    fi

    if [ ! -d "${repoDir}" ]; then
      echo "Cloning repository..."
      git clone -b "${branchName}" "${gitURL}" "${repoDir}"
    fi

    cd "${repoDir}"
    direnv allow || true

    if ${if cfg.source.updateOnBoot then "true" else "false"}; then
      echo "Updating repository..."
      git fetch origin "${branchName}" || {
        echo "ERROR: Failed to fetch origin/${branchName}"
        exit 1
      }

      if git show-ref --verify --quiet "refs/heads/${branchName}"; then
        git checkout "${branchName}" || {
          echo "ERROR: Failed to checkout local branch ${branchName}"
          exit 1
        }
      elif git show-ref --verify --quiet "refs/remotes/origin/${branchName}"; then
        git checkout -b "${branchName}" "origin/${branchName}" || {
          echo "ERROR: Failed to create tracking branch ${branchName}"
          exit 1
        }
      else
        echo "ERROR: Branch ${branchName} does not exist on origin"
        exit 1
      fi

      git reset --hard "origin/${branchName}" || {
        echo "ERROR: Failed to reset to origin/${branchName}"
        exit 1
      }
    else
      echo "Repository update disabled"
    fi

    echo "Ensuring lx-data-models dependency..."

    LX_MODELS_DIR="${repoDir}/libs/lx-data-models"

    mkdir -p "${repoDir}/libs"

    if [ ! -d "''${LX_MODELS_DIR}" ] || [ ! -f "''${LX_MODELS_DIR}/pyproject.toml" ]; then
      echo "lx-data-models missing or broken so re-cloning..."

      rm -rf "''${LX_MODELS_DIR}"

      git clone --branch report_template --single-branch \
        https://github.com/wg-lux/lx-data-models \
        "''${LX_MODELS_DIR}" || {
          echo "ERROR: Failed to clone lx-data-models"
          exit 1
      }

      echo "lx-data-models cloned successfully"
    else
      echo "lx-data-models already present"
    fi

    echo "Ensuring endoreg-db dependency..."

    ENDOREG_DB_DIR="${repoDir}/libs/endoreg-db"

    mkdir -p "${repoDir}/libs"

    if [ ! -d "''${ENDOREG_DB_DIR}" ] || [ ! -f "''${ENDOREG_DB_DIR}/pyproject.toml" ]; then
      echo "endoreg-db missing or broken so re-cloning..."

      rm -rf "''${ENDOREG_DB_DIR}"

      git clone --branch lx-ai-service --single-branch \
        https://github.com/wg-lux/endoreg-db \
        "''${ENDOREG_DB_DIR}" || {
          echo "ERROR: Failed to clone endoreg-db"
          exit 1
      }

      echo "endoreg-db cloned successfully"
    else
      echo "endoreg-db already present"
    fi

    echo "endoreg-db dependency is present for uv workspace sync"

    mkdir -p \
      "${envConfDir}" \
      "${envDataDir}" \
      "${envFrameDir}" \
      "${envFrameMaterializationOutputRoot}" \
      "${envTrainingRoot}" \
      "${envCheckpointsDir}" \
      "${envRunsDir}" \
      "${envBucketSnapshotDir}" \
      "${envCsvDir}" \
      "${repoDir}/.config/secretspec" \
      "${envPlaintextTmpDir}"

    if [ "${envProtectedDataDir}" = "${envDataDir}" ]; then
      mkdir -p \
        "${envProtectedDataDir}" \
        "${envStorageDir}" \
        "${envProcessedVideoDir}" \
        "${envStreamableVideoRoot}" \
        "${envStreamableVideoRawRoot}" \
        "${envStreamableVideoProcessedRoot}"
    else
      echo "Using external protected media root: ${envProtectedDataDir}"
      if [ ! -d "${envStorageDir}" ]; then
        echo "ERROR: External protected storage root does not exist: ${envStorageDir}" >&2
        echo "Set services.luxnix.lxAiLocal.runtime.protectedDataDir correctly or start the owning media service first." >&2
        exit 1
      fi
    fi

    export HOME_DIR="${endoreg-service-user-home}"
    export WORKING_DIR="${repoDir}"

    export DATA_DIR="${envDataDir}"
    export DJANGO_DATA_DIR="${envDataDir}"
    export LX_ANNOTATE_DATA_DIR="${envDataDir}"

    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${envProtectedDataDir}"
    export STORAGE_DIR="${envStorageDir}"
    export PROTECTED_MEDIA_ROOT="${envStorageDir}"

    export CONF_DIR="${envConfDir}"
    export FRAME_DIR="${envFrameDir}"
    export FRAME_MATERIALIZATION_OUTPUT_ROOT="${envFrameMaterializationOutputRoot}"

    export TRAINING_CONFIG_PATH="${repoDir}/lx_ai/ai_model_config/train_sandbox_postgres.yaml"

    export TRAINING_ROOT="${envTrainingRoot}"
    export CHECKPOINTS_DIR="${envCheckpointsDir}"
    export RUNS_DIR="${envRunsDir}"
    export BUCKET_SNAPSHOT_DIR="${envBucketSnapshotDir}"

    export BACKBONE_CHECKPOINT="${envBackboneCheckpoint}"
    export BACKBONE_CHECKPOINT_URL="${envBackboneCheckpointUrl}"

    export SQLITE_DB_PATH="${repoDir}/dev_db.sqlite"

    export LEGACY_IMAGE_DIR="${envLegacyImageDir}"
    export LEGACY_JSONL_PATH="${envLegacyJsonlPath}"

    export CSV_DIR="${envCsvDir}"

    export FRAME_PATH_REMAP_SOURCE=""
    export FRAME_PATH_REMAP_TARGET=""

    export DB_PWD_FILE="${envConfDir}/db_pwd"
    export DJANGO_DB_PASSWORD_FILE="${envConfDir}/db_pwd"

    export DJANGO_ENV="production"
    export DJANGO_DEBUG="False"
    export DJANGO_SETTINGS_MODULE="lx_ai.settings.settings_prod"
    export DJANGO_SETTINGS_MODULE_PRODUCTION="lx_ai.settings.settings_prod"
    export DJANGO_SETTINGS_MODULE_DEVELOPMENT="lx_ai.settings.settings_dev"

    export DJANGO_DB_ENGINE="django.db.backends.postgresql"
    export DJANGO_DB_NAME="${cfg.database.name}"
    export DJANGO_DB_USER="${cfg.database.user}"
    export DJANGO_DB_HOST="${cfg.database.host}"
    export DJANGO_DB_PORT="${toString cfg.database.port}"
    export DJANGO_DB_SSLMODE="${cfg.database.sslMode}"
    export DB_BACKEND="postgres"

    export LX_ANNOTATE_MASTER_KEY_FILE="${toString cfg.runtime.masterKeyFile}"

    export ENDOREG_DB_PLAINTEXT_TMP_DIR="${envPlaintextTmpDir}"

    export LX_ANNOTATE_STREAMABLE_VIDEO_ROOT="${envStreamableVideoRoot}"
    export LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT="${envStreamableVideoRawRoot}"
    export LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT="${envStreamableVideoProcessedRoot}"

    export LOG_LEVEL="INFO"

    DJANGO_DB_PASSWORD_VALUE="$(tr -d '\n' < "${envConfDir}/db_pwd" 2>/dev/null || true)"
    export DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD_VALUE"

    cat > "${repoDir}/.config/secretspec/config.toml" <<EOF
[defaults]
provider = "env"
profile = "production"
EOF

    cat > "${envSystemdFilePath}" <<EOF
HOME_DIR=${endoreg-service-user-home}
WORKING_DIR=${repoDir}

DATA_DIR=${envDataDir}
DJANGO_DATA_DIR=${envDataDir}
LX_ANNOTATE_DATA_DIR=${envDataDir}

LX_ANNOTATE_ENCRYPTED_DATA_DIR=${envProtectedDataDir}
STORAGE_DIR=${envStorageDir}
PROTECTED_MEDIA_ROOT=${envStorageDir}

CONF_DIR=${envConfDir}
FRAME_DIR=${envFrameDir}
FRAME_MATERIALIZATION_OUTPUT_ROOT=${envFrameMaterializationOutputRoot}
TRAINING_CONFIG_PATH=${repoDir}/lx_ai/ai_model_config/train_sandbox_postgres.yaml

TRAINING_ROOT=${envTrainingRoot}
CHECKPOINTS_DIR=${envCheckpointsDir}
RUNS_DIR=${envRunsDir}
BUCKET_SNAPSHOT_DIR=${envBucketSnapshotDir}

BACKBONE_CHECKPOINT=${envBackboneCheckpoint}
BACKBONE_CHECKPOINT_URL=${envBackboneCheckpointUrl}

SQLITE_DB_PATH=${repoDir}/dev_db.sqlite

LEGACY_IMAGE_DIR=${envLegacyImageDir}
LEGACY_JSONL_PATH=${envLegacyJsonlPath}

CSV_DIR=${envCsvDir}

FRAME_PATH_REMAP_SOURCE=
FRAME_PATH_REMAP_TARGET=

DB_PWD_FILE=${envConfDir}/db_pwd
DJANGO_DB_PASSWORD_FILE=${envConfDir}/db_pwd

DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_SETTINGS_MODULE=lx_ai.settings.settings_prod
DJANGO_SETTINGS_MODULE_PRODUCTION=lx_ai.settings.settings_prod
DJANGO_SETTINGS_MODULE_DEVELOPMENT=lx_ai.settings.settings_dev

DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=${cfg.database.name}
DJANGO_DB_USER=${cfg.database.user}
DJANGO_DB_HOST=${cfg.database.host}
DJANGO_DB_PORT=${toString cfg.database.port}
DJANGO_DB_SSLMODE=${cfg.database.sslMode}
DB_BACKEND=postgres

LX_ANNOTATE_MASTER_KEY_FILE=${toString cfg.runtime.masterKeyFile}

ENDOREG_DB_PLAINTEXT_TMP_DIR=${envPlaintextTmpDir}

LX_ANNOTATE_STREAMABLE_VIDEO_ROOT=${envStreamableVideoRoot}
LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT=${envStreamableVideoRawRoot}
LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT=${envStreamableVideoProcessedRoot}

LOG_LEVEL=INFO
EOF

    echo "Starting LX-AI training pipeline..."
    exec devenv shell -- bash -c '
      set -euo pipefail

      echo "Installing lx-data-models in editable mode inside devenv..."
      ${pkgs.uv}/bin/uv pip install -e libs/lx-data-models || {
        echo "ERROR: Failed to install lx-data-models"
        exit 1
      }

      echo "Installing endoreg-db in editable mode inside devenv..."
      ${pkgs.uv}/bin/uv pip install -e libs/endoreg-db || {
        echo "ERROR: Failed to install endoreg-db"
        exit 1
      }

      lxai_training
    '
  '';
in
{
  options.services.luxnix.lxAiLocal = {
    enable = mkBoolOpt false "Enable LxAI service";

    debug = mkOption {
      type = types.submodule {
        options = {
          enable = mkOption {
            type = types.bool;
            default = false;
            description = "Enable verbose debug output for lx-ai.";
          };
        };
      };
      default = { };
      description = "Debug configuration for lx-ai.";
    };

    source = mkOption {
      type = types.submodule {
        options = {
          url = mkOption {
            type = types.str;
            default = "https://github.com/wg-lux/lx-ai";
            description = "Git repository URL for lx-ai.";
          };

          branch = mkOption {
            type = types.str;
            default = "prototype";
            description = "Git branch to checkout for lx-ai.";
          };

          updateOnBoot = mkOption {
            type = types.bool;
            default = true;
            description = "Whether to update the lx-ai repository on service start.";
          };
        };
      };
      default = { };
      description = "Repository configuration for lx-ai.";
    };

    runtime = mkOption {
      type = types.submodule {
        options = {
          dataDir = mkOption {
            type = types.str;
            default = "data";
            description = ''
              lx-ai runtime data directory.

              Relative values are resolved inside the lx-ai repository.
              Absolute values are used as-is.

              This controls lx-ai outputs such as:
              - generated training frames
              - model training outputs
              - checkpoints
              - bucket snapshots
              - temporary plaintext materialization
            '';
          };

          protectedDataDir = mkOption {
            type = types.nullOr types.str;
            default = null;
            example = "/var/lib/lx-annotate/data";
            description = ''
              Protected data root used by endoreg-db for encrypted/protected media.

              When null, lx-ai uses runtime.dataDir as the protected media root.
              Set this to the lx-annotate protected data root when lx-ai should
              read videos produced by lx-annotate.

              endoreg-db resolves protected videos from:
                protectedDataDir/storage/processed_videos_final/<video>.mp4
            '';
          };

          confDir = mkOption {
            type = types.str;
            default = "conf";
            description = "lx-ai config directory. Relative values are resolved inside the lx-ai repository.";
          };

          backboneCheckpointUrl = mkOption {
            type = types.str;
            default = "";
            description = "URL for downloading the backbone checkpoint if not present locally.";
          };

          masterKeyFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/lx_annotate_master_key";
            description = "Application master key file used by endoreg-db encrypted storage.";
          };

          encryptionService = mkOption {
            type = types.nullOr types.str;
            default = null;
            example = "lx-annotate-encrypted-data.service";
            description = ''
              Optional systemd unit that must be started before lx-ai when
              protectedDataDir points to an encrypted/mounted media root.
            '';
          };
        };
      };
      default = { };
      description = "Runtime directory configuration for lx-ai.";
    };

    database = mkOption {
      type = types.submodule {
        options = {
          host = mkOption {
            type = types.str;
            default = "localhost";
          };

          port = mkOption {
            type = types.port;
            default = 5432;
          };

          name = mkOption {
            type = types.str;
            default = "endoregDbLocal";
          };

          user = mkOption {
            type = types.str;
            default = "endoregDbLocal";
          };

          passwordFile = mkOption {
            type = types.path;
            default = "/etc/secrets/vault/SCRT_local_password_maintenance_password";
            description = "Vault managed DB password";
          };

          sslMode = mkOption {
            type = types.str;
            default = "prefer";
          };

          endoregLocalUserPasswordFile = mkOption {
            type = types.path;
            default = "/var/lib/postgresql/endoregDbLocal.password";
            description = "Local postgres password file";
          };
        };
      };
      default = { };
      description = "Database configuration for lx-ai.";
    };
  };

  config = mkIf cfg.enable {
    luxnix.generic-settings.postgres.enable = true;

    systemd.tmpfiles.rules = [
      "d ${endoreg-service-user-home} 0751 ${endoreg-service-user-name} ${endoreg-service-group-name} - -"
    ];

    systemd.services."lx-ai-boot" = {
      description = "Clone lx-ai repository and run training pipeline";
      wantedBy = [ "multi-user.target" ];

      wants = [
        "postgres-endoreg-setup.service"
      ] ++ encryptionServiceUnits;

      after = [
        "postgres-endoreg-setup.service"
        "systemd-tmpfiles-setup.service"
      ] ++ encryptionServiceUnits;

      requires = [
        "postgres-endoreg-setup.service"
        "systemd-tmpfiles-setup.service"
      ] ++ encryptionServiceUnits;

      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        WorkingDirectory = endoreg-service-user-home;

        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:${pkgs.uv}/bin:/run/current-system/sw/bin"
          "NIX_PATH=nixpkgs=${pkgs.path}"
        ];

        ExecStartPre = "+${pkgs.writeShellScript "lx-ai-pre-start" ''
          set -euo pipefail

          if [ -e ${repoDir} ]; then
            ${pkgs.coreutils}/bin/chown -R ${endoreg-service-user-name}:${endoreg-service-group-name} ${repoDir}
          fi

          mkdir -p ${envConfDir}

          SOURCE_PWD="${cfg.database.endoregLocalUserPasswordFile}"
          TARGET_PWD="${envConfDir}/db_pwd"

          if [ -f "$SOURCE_PWD" ]; then
            echo "Copying database password..."
            cp "$SOURCE_PWD" "$TARGET_PWD"
            chown ${endoreg-service-user-name}:${endoreg-service-group-name} "$TARGET_PWD"
            chmod 600 "$TARGET_PWD"
          else
            echo "WARNING: DB password file missing: $SOURCE_PWD"
          fi

          chown -R ${endoreg-service-user-name}:${endoreg-service-group-name} ${envConfDir}

          if [ -f "${toString cfg.runtime.masterKeyFile}" ]; then
            chown root:${endoreg-service-group-name} "${toString cfg.runtime.masterKeyFile}" || true
            chmod 640 "${toString cfg.runtime.masterKeyFile}" || true
          else
            echo "ERROR: LX-AI production requires the application master key file: ${toString cfg.runtime.masterKeyFile}" >&2
            echo "This must be the same LX_ANNOTATE_MASTER_KEY_FILE used by lx-annotate/endoreg-db for encrypted media." >&2
            exit 1
          fi
        ''}";

        ExecStart = "${runLxAiTraining}/bin/${scriptName}";
        TimeoutStartSec = "infinity";

        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;

        ReadWritePaths = lib.unique [
          endoreg-service-user-home

          envConfDir

          envDataDir
          envFrameDir
          envFrameMaterializationOutputRoot
          envTrainingRoot
          envCheckpointsDir
          envRunsDir
          envBucketSnapshotDir
          envPlaintextTmpDir

          envProtectedDataDir
          envStorageDir
          envProcessedVideoDir
          envStreamableVideoRoot
          envStreamableVideoRawRoot
          envStreamableVideoProcessedRoot
        ];

        MemoryMax = "8G";
        CPUQuota = "800%";
        Nice = 10;
        IOSchedulingClass = "best-effort";
        IOSchedulingPriority = 6;
        OOMScoreAdjust = 250;
      };
    };
  };
}