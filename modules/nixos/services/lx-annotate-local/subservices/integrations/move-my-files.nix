# Purpose: Define only the move-my-files.service unit.
# Command: Overlay-only; preserves the external service command.
{ ctx }:
with ctx;
{
  systemd.services.move-my-files = mkIf config.services.luxnix.fileMover.enable {
    after = mkAfter [ "lx-annotate-runtime-env.service" ];
    # Requisite (not Wants) — if runtime-env is not already active, move-my-files
    # exits immediately rather than pulling it in and racing with lx-annotate startup.
    # Files remain in source dirs; the path unit retries on the next change.
    unitConfig = {
      Requisite = "lx-annotate-runtime-env.service";
    };
    serviceConfig = mkIf cfg.runtime.frontendRequestThrottle.enable {
      Slice = "lx-annotate-background.slice";
    };
  };
}
