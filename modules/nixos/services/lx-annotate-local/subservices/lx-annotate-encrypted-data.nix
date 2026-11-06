# Purpose: Define only the lx-annotate-encrypted-data.service unit.
# Command: lx-annotate-encrypted-data-mount; ExecStop unmounts the volume.
{ ctx }:
with ctx;
{
  systemd.services.lx-annotate-encrypted-data = mkIf cfg.runtime.managedEncryptedData.enable {
    description = "Unlock and mount encrypted data volume for lx-annotate";
    wantedBy = [ "multi-user.target" ];
    before = [ "lx-annotate.service" ];
    after = [ "systemd-tmpfiles-setup.service" ] ++ cfg.runtime.managedEncryptedData.after;
    requires = cfg.runtime.managedEncryptedData.requires;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = "root";
      Group = "root";
      ExecStart = "${lxAnnotateEncryptedDataMountScript}/bin/lx-annotate-encrypted-data-mount";
      ExecStop = "${lxAnnotateEncryptedDataUmountScript}/bin/lx-annotate-encrypted-data-umount";
      LogNamespace = lxAnnotateJournalNamespace;
      TimeoutStartSec = "2min";
      TimeoutStopSec = "2min";
    };
    path = [
      pkgs.coreutils
      pkgs.cryptsetup
      pkgs.util-linux
    ];
  };
}
