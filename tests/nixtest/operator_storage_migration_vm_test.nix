{ repoRoot, ... }:
let
  storageNode =
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
    };
in
{
  name = "operator-storage-migration";
  nodes.machine = { pkgs, ... }: {
    imports = [ storageNode ];
    virtualisation.emptyDiskImages = [ 256 ];
    environment.systemPackages = [
      pkgs.cryptsetup
      pkgs.e2fsprogs
    ];
    luxnix.storage.operatorUnlocked = {
      layout = "legacy-containers";
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
  nodes.locked = { lib, pkgs, ... }: {
    imports = [ storageNode ];
    environment.systemPackages = [
      pkgs.cryptsetup
      pkgs.e2fsprogs
    ];
    luxnix.storage.operatorUnlocked = {
      layout = "legacy-containers";
      enable = true;
      migration.enable = false;
      volumes.pending = {
        container = "/root/pending.luks";
        mountPoint = "/srv/pending";
      };
      guardedServices.locked-consumer = [ "/srv/pending" ];
    };
    # Exercise the actual prompt timeout quickly; host evaluation checks 90/120s.
    systemd.services = {
      luxnix-storage-unlock-pending = {
        serviceConfig.TimeoutStartSec = lib.mkForce "5s";
        unitConfig.JobTimeoutSec = lib.mkForce "10s";
      };
      locked-consumer = {
        wantedBy = [ "multi-user.target" ];
        script = "touch /srv/pending/consumer-started";
        serviceConfig.Type = "oneshot";
        serviceConfig.RemainAfterExit = true;
      };
      # A lightweight login milestone with the production display-manager ordering.
      display-manager = {
        wantedBy = [ "multi-user.target" ];
        script = "touch /run/login-reached";
        serviceConfig.Type = "oneshot";
        serviceConfig.RemainAfterExit = true;
      };
    };
    services.openssh.enable = true;
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
    locked.start()
    locked.wait_for_unit("multi-user.target")
    locked.succeed("dd if=/dev/urandom of=/root/test-key bs=32 count=1 status=none; chmod 600 /root/test-key")
    locked.succeed("truncate -s 64M /root/pending.luks")
    locked.succeed("cryptsetup luksFormat --type luks2 --batch-mode --key-file /root/test-key /root/pending.luks")
    locked.succeed("cryptsetup open --key-file /root/test-key /root/pending.luks pending; mkfs.ext4 -q /dev/mapper/pending; cryptsetup close pending")
    locked.shutdown()
    locked.start()
    locked.wait_for_unit("multi-user.target", timeout=60)
    # No answer to the real systemd password request: login and SSH still recover.
    locked.succeed("test -e /run/login-reached")
    locked.wait_for_open_port(22)
    locked.succeed("systemctl is-failed luxnix-storage-unlock-pending.service")
    assert locked.succeed("systemctl show luxnix-storage-unlock-pending.service -p Result --value").strip() == "timeout"
    locked.fail("test -e /dev/mapper/pending")
    locked.fail("mountpoint /srv/pending")
    locked.fail("test -e /srv/pending/consumer-started")
    # An authorized unlock after timeout can recover without reboot or plaintext fallback.
    locked.succeed("cryptsetup open --key-file /root/test-key /root/pending.luks pending")
    locked.succeed("systemctl start locked-consumer.service")
    locked.succeed("mountpoint /srv/pending; test -e /srv/pending/consumer-started")
  '';
}
