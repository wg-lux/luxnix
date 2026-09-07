# Purpose: Define only the lx-annotate-acceptance.service unit.
# Command: Application checks, worker activity checks, and HTTPS static-manifest probe.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-acceptance = {
    description = "Run LX-Annotate live web, worker, storage, and static acceptance checks";
    after = [
      "lx-annotate-preflight.service"
      "lx-annotate.service"
      "nginx.service"
    ]
    ++ alwaysWorkerServiceUnits
    ++ encryptionServiceUnits;
    wants = [
      "lx-annotate-preflight.service"
      "lx-annotate.service"
      "nginx.service"
    ]
    ++ alwaysWorkerServiceUnits
    ++ encryptionServiceUnits;
    requires = [
      "lx-annotate-preflight.service"
      "lx-annotate.service"
      "nginx.service"
    ]
    ++ alwaysWorkerServiceUnits
    ++ encryptionServiceUnits;
    unitConfig = encryptedDataMountUnitConfig;
    environment = commonExtraEnv;
    serviceConfig = {
      Type = "oneshot";
      User = endoreg-service-user-name;
      Group = endoreg-service-group-name;
      WorkingDirectory = runtimeDataRootPath;
      EnvironmentFile = envSystemdFilePath;
      ExecStart = pkgs.writeShellScript "lx-annotate-acceptance" ''
        set -euo pipefail
        ${effectiveRuntimePackage}/bin/lx-annotate-manage check --fail-level CRITICAL
        ${effectiveRuntimePackage}/bin/lx-annotate-manage verify_encrypted_storage
        required_workers=( ${lib.concatMapStringsSep " " lib.escapeShellArg alwaysWorkerServiceUnits} )
        for worker_unit in "''${required_workers[@]}"; do
          ${pkgs.systemd}/bin/systemctl is-active --quiet "$worker_unit"
        done
        ${pkgs.curl}/bin/curl --fail --silent --show-error \
          --cacert "${publicSslCertificatePath}" \
          --resolve "${cfg.django.hostname}:443:127.0.0.1" \
          "https://${cfg.django.hostname}/static/.vite/manifest.json" >/dev/null
      '';
      ReadWritePaths = appReadWritePaths;
    };
  };
}
