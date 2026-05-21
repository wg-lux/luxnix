{ lib
, cfg
, repoDir
}:

let
  defaults = {
    # lx-ai owned output/runtime root.
    #
    # Relative value means:
    #   /var/endoreg-service-user/lx-ai/data
    #
    # This is where lx-ai writes generated frames, checkpoints, runs,
    # bucket snapshots, and temporary plaintext materialization.
    dataDir = "data";

    # Protected media root used by endoreg-db path resolution.
    #
    # This is intentionally lx-annotate's protected data root, because
    # lx-annotate owns/imports/encrypts processed videos.
    #
    # endoreg-db resolves:
    #   VideoFile.processed_file = processed_videos_final/<hash>.mp4
    #
    # to:
    #   protectedDataDir/storage/processed_videos_final/<hash>.mp4
    protectedDataDir = "/var/lib/lx-annotate/data";

    # lx-ai config directory.
    # Relative value means:
    #   /var/endoreg-service-user/lx-ai/conf
    confDir = "conf";

    # Set this to "lx-annotate-encrypted-data.service" only if the
    # protectedDataDir depends on that systemd unit being mounted/unlocked
    # before lx-ai starts.
    #
    # Keep null if /var/lib/lx-annotate/data is already available normally.
    encryptionService = null;
  };

  makeRuntimePath = path:
    if lib.hasPrefix "/" path
    then path
    else "${repoDir}/${path}";

  # lx-ai owned runtime/output root.
  envDataDir = makeRuntimePath cfg.runtime.dataDir;

  # Protected media root used by endoreg-db.
  #
  # If protectedDataDir is null, lx-ai uses its own data dir.
  # If protectedDataDir is absolute, it is used as-is.
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
  envStorageDir = "${envProtectedDataDir}/storage";
  envProcessedVideoDir = "${envStorageDir}/processed_videos_final";

  envPlaintextTmpDir = "${envDataDir}/temp/plaintext_media";

  envStreamableVideoRoot = "${envStorageDir}/streamable_videos";
  envStreamableVideoRawRoot = "${envStreamableVideoRoot}/raw";
  envStreamableVideoProcessedRoot = "${envStreamableVideoRoot}/processed";

  envSystemdFilePath = "${repoDir}/.env.systemd";
in
{
  inherit
    defaults
    makeRuntimePath

    envDataDir
    envProtectedDataDir
    envConfDir

    envFrameDir
    envFrameMaterializationOutputRoot

    envTrainingRoot
    envCheckpointsDir
    envRunsDir
    envBucketSnapshotDir
    envBackboneCheckpoint
    envBackboneCheckpointUrl

    envCsvDir
    envLegacyImageDir
    envLegacyJsonlPath

    envStorageDir
    envProcessedVideoDir

    envPlaintextTmpDir

    envStreamableVideoRoot
    envStreamableVideoRawRoot
    envStreamableVideoProcessedRoot

    envSystemdFilePath;
}