# Purpose: Define only the move-my-files.service unit.
# Command: Overlay-only; preserves the external service command.
{ ctx }:
with ctx;
{
  systemd.services.move-my-files = mkIf config.services.luxnix.fileMover.enable {
    after = mkAfter [ "lx-annotate-runtime-env.service" ];
    wants = mkAfter [ "lx-annotate-runtime-env.service" ];
  };
}
