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
  envDataDir = "${repoDir}/${cfg.runtime.dataDir}";
  envConfDir = "${repoDir}/${cfg.runtime.confDir}";
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

  envStorageDir = "${envDataDir}/storage";
  envProcessedVideoDir = "${envStorageDir}/processed_videos_final";

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
      echo "Installing lx-data-models in editable mode..."
      ${pkgs.uv}/bin/uv pip install -e "''${LX_MODELS_DIR}" || {
        echo "ERROR: Failed to install lx-data-models"
        exit 1
      }
    else
      echo "lx-data-models already present"
    fi

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
      "${envStorageDir}" \
      "${envProcessedVideoDir}" \
      "${envDataDir}/temp/plaintext_media" \
      "${envStorageDir}/streamable_videos" \
      "${envStorageDir}/streamable_videos/raw" \
      "${envStorageDir}/streamable_videos/processed"


    export HOME_DIR="${endoreg-service-user-home}"
    export WORKING_DIR="${repoDir}"

    export DATA_DIR="${envDataDir}"
    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${envDataDir}"
    export STORAGE_DIR="${envDataDir}/storage"
    export PROTECTED_MEDIA_ROOT="${envDataDir}/storage"
    
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
    export LX_ANNOTATE_DATA_DIR="${envDataDir}"
    export LX_ANNOTATE_ENCRYPTED_DATA_DIR="${envDataDir}"
    export DJANGO_DATA_DIR="${envDataDir}"
    export PROTECTED_MEDIA_ROOT="${envStorageDir}"
    export ENDOREG_DB_PLAINTEXT_TMP_DIR="${envDataDir}/temp/plaintext_media"
    export LX_ANNOTATE_STREAMABLE_VIDEO_ROOT="${envStorageDir}/streamable_videos"
    export LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT="${envStorageDir}/streamable_videos/raw"
    export LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT="${envStorageDir}/streamable_videos/processed"

    export LOG_LEVEL="INFO"

    DJANGO_DB_PASSWORD_VALUE="$(tr -d '\n' < "${envConfDir}/db_pwd" 2>/dev/null || true)"
    export DJANGO_DB_PASSWORD="$DJANGO_DB_PASSWORD_VALUE"

    cat > "${repoDir}/.config/secretspec/config.toml" <<EOF
[defaults]
provider = "env"
profile = "production"
EOF

cat > "${repoDir}/.env.systemd" <<EOF
HOME_DIR=${endoreg-service-user-home}
WORKING_DIR=${repoDir}
LX_ANNOTATE_ENCRYPTED_DATA_DIR=${envDataDir}
DATA_DIR=${envDataDir}
STORAGE_DIR=${envStorageDir}
PROTECTED_MEDIA_ROOT=${envStorageDir}
DJANGO_DATA_DIR=${envDataDir}
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

LEGACY_IMAGE_DIR=${envLegacyImageDir}
LEGACY_JSONL_PATH=${envLegacyJsonlPath}

CSV_DIR=${envCsvDir}
LX_ANNOTATE_MASTER_KEY_FILE=${toString cfg.runtime.masterKeyFile}
LX_ANNOTATE_DATA_DIR=${envDataDir}

DJANGO_DATA_DIR=${envDataDir}
STORAGE_DIR=${envStorageDir}
PROTECTED_MEDIA_ROOT=${envStorageDir}

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

ENDOREG_DB_PLAINTEXT_TMP_DIR=${envDataDir}/temp/plaintext_media
LX_ANNOTATE_STREAMABLE_VIDEO_ROOT=${envStorageDir}/streamable_videos
LX_ANNOTATE_STREAMABLE_VIDEO_RAW_ROOT=${envStorageDir}/streamable_videos/raw
LX_ANNOTATE_STREAMABLE_VIDEO_PROCESSED_ROOT=${envStorageDir}/streamable_videos/processed
DB_BACKEND=postgres

LOG_LEVEL=INFO
EOF

    echo "Starting LX-AI training pipeline..."
    exec devenv shell -- bash -c "lxai_training"
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
            description = "Relative path to lx-ai data directory inside the repository.";
          };

          confDir = mkOption {
            type = types.str;
            default = "conf";
            description = "Relative path to lx-ai config directory inside the repository.";
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
      wants = [ "postgres-endoreg-setup.service" ];
      after = [ "postgres-endoreg-setup.service" "systemd-tmpfiles-setup.service" ];
      requires = [ "postgres-endoreg-setup.service" "systemd-tmpfiles-setup.service" ];

      serviceConfig = {
        Type = "oneshot";
        User = endoreg-service-user-name;
        WorkingDirectory = endoreg-service-user-home;

        Environment = [
          "PATH=${pkgs.git}/bin:${pkgs.devenv}/bin:${pkgs.direnv}/bin:/run/current-system/sw/bin"
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
            echo "WARNING: LX-AI encryption master key file missing: ${toString cfg.runtime.masterKeyFile}"
          fi
        ''}";

        ExecStart = "${runLxAiTraining}/bin/${scriptName}";
        TimeoutStartSec = "infinity";

        ProtectSystem = "full";
        PrivateTmp = true;
        NoNewPrivileges = true;
        ReadWritePaths = [
          endoreg-service-user-home
          envDataDir
          envStorageDir
          envProcessedVideoDir
          envConfDir
          envFrameDir
          envFrameMaterializationOutputRoot
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
