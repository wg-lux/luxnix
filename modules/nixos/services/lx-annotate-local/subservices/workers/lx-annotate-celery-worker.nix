# Purpose: Define only the lx-annotate-celery-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the maintenance and default queues.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-worker = workerServices.lx-annotate-celery-worker;

  systemd.timers.lx-annotate-celery-worker = workerTimers.lx-annotate-celery-worker;
}
