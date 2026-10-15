{
  lib,
  ...
}:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal.runtime.monitoring = {
    enable = mkOption {
      type = types.bool;
      default = true;
      description = "Expose the immutable host-owned monitoring inventory to LX-Annotate.";
    };
    deploymentRevision = mkOption {
      type = types.nullOr (types.strMatching "[0-9a-f]{7,64}");
      default = null;
      description = "Optional deployed release revision reported by the monitoring snapshot. Null uses immutable source provenance when available.";
    };
    systemctlTimeoutSeconds = mkOption {
      type = types.ints.between 1 5;
      default = 3;
      description = "Bounded timeout for read-only systemctl show queries made by the application monitoring snapshot.";
    };
    diskWarningFreePercent = mkOption {
      type = types.ints.between 1 99;
      default = 10;
      description = "Free-space percentage at or below which monitoring reports a warning.";
    };
    diskErrorFreePercent = mkOption {
      type = types.ints.between 1 99;
      default = 5;
      description = "Free-space percentage at or below which monitoring reports an error.";
    };
    pendingWarningSeconds = mkOption {
      type = types.ints.between 60 604800;
      default = 3600;
      description = "Age after which a pending operational job is reported as delayed.";
    };
    recentFailureWindowSeconds = mkOption {
      type = types.ints.between 60 604800;
      default = 86400;
      description = "Lookback window used to summarize recent terminal failures.";
    };
  };
}
