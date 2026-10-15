# Purpose: Compose the one-service Celery modules without declaring units here.
# Command: None; commands are documented in each worker module.
{ ctx }:
map (modulePath: import modulePath { inherit ctx; }) [
  ./workers/lx-annotate-celery-beat.nix
  ./workers/lx-annotate-celery-worker.nix
  ./workers/lx-annotate-celery-hub-transfer-worker.nix
  ./workers/lx-annotate-celery-pipeline-worker.nix
  ./workers/lx-annotate-celery-frame-extraction-worker.nix
  ./workers/lx-annotate-celery-ffmpeg-worker.nix
  ./workers/lx-annotate-celery-inference-worker.nix
  ./workers/lx-annotate-celery-training-worker.nix
  ./workers/lx-annotate-celery-llm-inference-worker.nix
]
