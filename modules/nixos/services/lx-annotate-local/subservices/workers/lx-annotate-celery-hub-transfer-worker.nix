# Purpose: Define only the lx-annotate-celery-hub-transfer-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the hub_transfer queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-hub-transfer-worker =
    workerServices.lx-annotate-celery-hub-transfer-worker;

  systemd.timers.lx-annotate-celery-hub-transfer-worker =
    workerTimers.lx-annotate-celery-hub-transfer-worker;
}
