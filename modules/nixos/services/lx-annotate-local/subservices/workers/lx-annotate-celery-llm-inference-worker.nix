# Purpose: Define only the lx-annotate-celery-llm-inference-worker.service unit and its matching conditional timer.
# Command: lx-annotate-worker for the llm_inference queue.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-llm-inference-worker =
    workerServices.lx-annotate-celery-llm-inference-worker;

  systemd.timers.lx-annotate-celery-llm-inference-worker =
    workerTimers.lx-annotate-celery-llm-inference-worker;
}
