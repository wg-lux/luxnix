# Purpose: Define only the lx-annotate-celery-ffmpeg-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the ffmpeg_media queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-ffmpeg-worker = workerServices.lx-annotate-celery-ffmpeg-worker;

  systemd.timers.lx-annotate-celery-ffmpeg-worker = workerTimers.lx-annotate-celery-ffmpeg-worker;
}
