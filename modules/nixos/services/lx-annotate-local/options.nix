args: {
  imports = map (modulePath: import modulePath args) [
    ./options/enable.nix
    ./options/debug.nix
    ./options/runtime.nix
    ./options/monitoring.nix
    ./options/django.nix
    ./options/database.nix
    ./options/data-recovery.nix
    ./options/center-admin-bootstrap.nix
    ./options/streamable-migration.nix
    ./options/hls-materialization.nix
    ./options/hls-backfill.nix
    ./options/data-cleanup.nix
    ./options/storage-relief.nix
    ./options/hub.nix
    ./options/remote-access.nix
  ];
}
