# Purpose: Define only the lx-annotate-celery-frame-extraction-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the frame_extraction queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-frame-extraction-worker =
    workerServices.lx-annotate-celery-frame-extraction-worker;

  systemd.timers.lx-annotate-celery-frame-extraction-worker =
    workerTimers.lx-annotate-celery-frame-extraction-worker;
}
