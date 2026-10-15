# Purpose: Order the package-provided knowledge-base bootstrap after wheel preparation.
# Command: lx-dtypes-kb-registry bootstrap (owned by the upstream module).
{ ctx }:
with ctx;
{
  systemd.services.lx-dtypes-kb-bootstrap = mkIf useWheelRuntime {
    after = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-wheel-runtime.service"
    ]
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-runtime-env.service"
      "lx-annotate-wheel-runtime.service"
    ]
    ++ encryptionServiceUnits;
    restartTriggers = [ effectiveRuntimePackage ];
    unitConfig = encryptedDataMountUnitConfig;
  };
}
