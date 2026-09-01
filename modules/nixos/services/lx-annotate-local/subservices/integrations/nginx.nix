# Purpose: Define only the nginx.service unit.
# Command: Overlay-only; preserves the upstream nginx command.
{ ctx }:
with ctx;
{
  systemd.services.nginx.serviceConfig = {
    Nice = -5;
    IOSchedulingClass = "best-effort";
    IOSchedulingPriority = 0;
    OOMScoreAdjust = -500;
  };
}
