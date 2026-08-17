{
  celeryBeatService,
  workerServices,
  workerTimers,
  ...
}:
{
  systemd.services = {
    lx-annotate-celery-beat = celeryBeatService;
    inherit (workerServices)
      lx-annotate-celery-ffmpeg-worker
      lx-annotate-celery-frame-extraction-worker
      lx-annotate-celery-hub-transfer-worker
      lx-annotate-celery-inference-worker
      lx-annotate-celery-llm-inference-worker
      lx-annotate-celery-pipeline-worker
      lx-annotate-celery-training-worker
      lx-annotate-celery-worker
      ;
  };
  systemd.timers = workerTimers;
}
