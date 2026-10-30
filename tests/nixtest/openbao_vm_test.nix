{ repoRoot, ... }:
{
  name = "openbao-release";
  nodes.server =
    { lib, pkgs, ... }:
    {
      imports = [ "${repoRoot}/modules/nixos/luxnix/openbao" ];
      virtualisation = {
        memorySize = 2048;
        emptyDiskImages = [ 512 ];
        fileSystems."/var/lib/openbao" = {
          device = "/dev/mapper/bao-test";
          fsType = "ext4";
          options = [ "noauto" ];
        };
      };
      environment.systemPackages = with pkgs; [
        cryptsetup
        e2fsprogs
        openssl
        python3
      ];
      environment.etc."openbao-release-test.py".source = ./openbao_release.py;
      luxnix.openbao = {
        enable = true;
        tlsCertificateFile = "/run/bao-test/server.pem";
        tlsKeyFile = "/run/bao-test/server.key";
      };
      # Delay startup only; retain every production unit sandbox and storage guard.
      systemd.services.openbao.wantedBy = lib.mkForce [ ];
      system.stateVersion = "26.05";
    };
  testScript = ''
    server.start()
    server.wait_for_unit("multi-user.target")
    server.succeed("python /etc/openbao-release-test.py prepare")
    # Only the disposable VM disk is formatted. Keys never leave the guest.
    server.succeed("cryptsetup luksFormat --type luks2 --batch-mode --key-file /run/bao-test/disk.key /dev/vdb")
    server.succeed("cryptsetup open --key-file /run/bao-test/disk.key /dev/vdb bao-test")
    server.succeed("mkfs.ext4 -q /dev/mapper/bao-test")
    # A mountpoint alone is insufficient: the real ExecStartPre must reject tmpfs.
    server.succeed("mkdir -p /var/lib/openbao; mount -t tmpfs tmpfs /var/lib/openbao")
    server.fail("systemctl start openbao.service")
    server.succeed("journalctl -u openbao --no-pager | grep -F 'Secret storage boundary verification failed'")
    server.succeed("systemctl stop openbao.service var-lib-openbao.mount")
    server.succeed("systemctl start openbao.service")
    server.wait_for_unit("openbao.service")
    server.succeed("python /etc/openbao-release-test.py exercise")
    server.succeed("systemctl restart openbao.service")
    server.wait_for_unit("openbao.service")
    server.succeed("python /etc/openbao-release-test.py sealed")
  '';
}
