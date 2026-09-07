args: {
  imports = [
    (import ./options/enable.nix args)
    (import ./options/debug.nix args)
    (import ./options/source.nix args)
    (import ./options/runtime.nix args)
    (import ./options/django.nix args)
    (import ./options/database.nix args)
    (import ./options/data-recovery.nix args)
    (import ./options/center-admin-bootstrap.nix args)
    (import ./options/streamable-migration.nix args)
    (import ./options/hls-materialization.nix args)
    (import ./options/hls-backfill.nix args)
    (import ./options/data-cleanup.nix args)
    (import ./options/storage-relief.nix args)
    (import ./options/hub.nix args)
  ];
}
