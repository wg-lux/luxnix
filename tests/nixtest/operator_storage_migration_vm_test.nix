{ repoRoot, ... }:
{
  name = "operator-storage-migration";
  nodes.machine =
    {
      config,
      lib,
      pkgs,
      utils,
      ...
    }:
    {
      imports = [ "${repoRoot}/modules/nixos/luxnix/operator-unlocked-storage" ];
      # The VM module replaces fileSystems; retain the module-generated test mounts.
      virtualisation.fileSystems =
        (import "${repoRoot}/modules/nixos/luxnix/operator-unlocked-storage" {
          inherit
            config
            lib
            pkgs
            utils
            ;
        }).config.content.fileSystems;
      virtualisation.emptyDiskImages = [ 256 ];
      environment.systemPackages = [
        pkgs.cryptsetup
        pkgs.e2fsprogs
      ];
      luxnix.storage.operatorUnlocked = {
        enable = true;
        volumes.private = {
          device = "/dev/mapper/test-data";
          mountPoint = "/srv/encrypted";
        };
        bindMounts."/srv/plain" = {
          volume = "private";
          directory = "payload";
        };
        guardedServices.consumer = [ "/srv/plain" ];
        startupServices = [ "consumer" ];
      };
      systemd.tmpfiles.rules = [ "d /srv/plain/quarantine 0700 root root -" ];
      systemd.services.consumer = {
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = "test -s /srv/plain/record";
      };
      system.stateVersion = "26.05";
    };
  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    # Ephemeral VM test key; no production passphrase or filesystem is involved.
    machine.succeed("dd if=/dev/urandom of=/root/test-key bs=32 count=1 status=none; chmod 600 /root/test-key")
    machine.succeed("cryptsetup luksFormat --type luks2 --batch-mode --key-file /root/test-key /dev/vdb")
    machine.succeed("cryptsetup open --key-file /root/test-key /dev/vdb test-data; mkfs.ext4 -q /dev/mapper/test-data")
    machine.succeed("printf original > /srv/plain/record; chmod 600 /srv/plain/record")
    machine.succeed("systemctl start luxnix-storage-precopy.service")
    machine.fail("mountpoint /srv/plain")
    machine.succeed("test -s /srv/encrypted/payload.luxnix-copy/data/record")
    machine.succeed("printf final-delta > /srv/plain/record")
    machine.succeed("systemctl start luxnix-storage-cutover.service")
    machine.succeed("systemctl start consumer.service")
    machine.succeed("mountpoint /srv/plain; mountpoint /srv/encrypted")
    assert machine.succeed("cat /srv/plain/record") == "final-delta"
    assert machine.succeed("stat -c %a /srv/plain/quarantine").strip() == "700"
    machine.succeed("mkdir /run/original; mount --bind / /run/original")
    assert machine.succeed("cat /run/original/srv/plain/record") == "final-delta"
    machine.succeed("printf current > /srv/plain/record")
    machine.succeed("systemctl stop consumer.service srv-plain.mount srv-encrypted.mount")
    machine.succeed("systemctl start consumer.service")
    assert machine.succeed("cat /srv/plain/record") == "current"
    machine.shutdown()
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("cryptsetup open --key-file /root/test-key /dev/vdb test-data")
    machine.succeed("systemctl start consumer.service")
    assert machine.succeed("cat /srv/plain/record") == "current"
  '';
}
