# Purpose: Define only the lx-annotate-celery-pipeline-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the pipeline queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-pipeline-worker =
    workerServices.lx-annotate-celery-pipeline-worker;

  systemd.timers.lx-annotate-celery-pipeline-worker = workerTimers.lx-annotate-celery-pipeline-worker;
}
