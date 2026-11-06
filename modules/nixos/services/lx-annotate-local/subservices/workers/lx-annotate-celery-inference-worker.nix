# Purpose: Define only the lx-annotate-celery-inference-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the inference queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-inference-worker =
    workerServices.lx-annotate-celery-inference-worker;

  systemd.timers.lx-annotate-celery-inference-worker =
    workerTimers.lx-annotate-celery-inference-worker;
}
