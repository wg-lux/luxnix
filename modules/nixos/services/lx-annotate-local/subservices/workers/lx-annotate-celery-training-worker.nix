# Purpose: Define only the lx-annotate-celery-training-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the model_training queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-training-worker =
    workerServices.lx-annotate-celery-training-worker;

  systemd.timers.lx-annotate-celery-training-worker = workerTimers.lx-annotate-celery-training-worker;
}
