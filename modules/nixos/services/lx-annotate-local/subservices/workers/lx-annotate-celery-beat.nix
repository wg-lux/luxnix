# Purpose: Define only the lx-annotate-celery-beat.service unit.
# Command: lx-annotate-celery beat --loglevel=INFO with its persistent schedule file.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-celery-beat = celeryBeatService;
}
