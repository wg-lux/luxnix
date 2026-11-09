# Destructive provisioning is confined to disposable QEMU disks and test keys.
{
  pkgs,
  disko,
  repoRoot,
  remoteUnlockTest ? false,
  mdraidTest ? false,
  deferStartupTest ? false,
  plaintextRootTest ? false,
}:
let
  key = "/etc/luks-keys/lx-data.key";
  sshFixtures = pkgs.path + "/nixos/tests/initrd-network-ssh";
  dataLuks = {
    type = "luks";
    name = "lx-data";
    initrdUnlock = false;
    settings.keyFile = key;
    extraFormatArgs = [
      "--type"
      "luks2"
    ];
    content = {
      type = "btrfs";
      subvolumes.application.mountpoint = "/srv/data";
    };
  };
  raw = {
    disko.devices.disk = {
      system = {
        type = "disk";
        device = "/dev/vda";
        content = {
          type = "gpt";
          partitions = {
            ESP = {
              size = "256M";
              type = "EF00";
              content = {
                type = "filesystem";
                format = "vfat";
                mountpoint = "/boot";
              };
            };
            root = {
              size = "100%";
              content = {
                type = "luks";
                name = "cryptroot";
                passwordFile = "/tmp/secret.key";
                extraFormatArgs = [
                  "--type"
                  "luks2"
                ];
                content =
                  if plaintextRootTest then
                    {
                      type = "btrfs";
                      subvolumes = {
                        root.mountpoint = "/";
                        home.mountpoint = "/home";
                        nix.mountpoint = "/nix";
                      };
                    }
                  else
                    {
                      type = "filesystem";
                      format = "ext4";
                      mountpoint = "/";
                    };
              };
            };
          };
        };
      };
      data = {
        type = "disk";
        device = "/dev/vdb";
        content = {
          type = "gpt";
          partitions.data = {
            size = "100%";
            content =
              if mdraidTest then
                {
                  type = "mdraid";
                  name = "application";
                }
              else
                dataLuks;
          };
        };
      };
    };
    disko.devices.mdadm = pkgs.lib.optionalAttrs mdraidTest {
      application = {
        type = "mdadm";
        level = 1;
        metadata = "1.2";
        content = dataLuks;
      };
    };
  };
in
disko.lib.testLib.makeDiskoTest {
  inherit pkgs;
  name =
    if plaintextRootTest then
      "boot-storage-plaintext"
    else if mdraidTest then
      "boot-storage-mdraid"
    else if deferStartupTest then
      "boot-storage-deferred"
    else if remoteUnlockTest then
      "boot-storage-remote"
    else
      "boot-storage";
  disko-config = raw;
  extraInstallerConfig = { pkgs, ... }: {
    environment.systemPackages = pkgs.lib.optionals plaintextRootTest [
      pkgs.cryptsetup
      pkgs.btrfs-progs
    ];
    environment.etc."test-initrd-host-key" = pkgs.lib.mkIf remoteUnlockTest {
      source = sshFixtures + "/ssh_host_ed25519_key";
      mode = "0600";
    };
    system.activationScripts.testSecondaryKey = ''
      install -d -m 0700 /etc/luks-keys
      ${pkgs.coreutils}/bin/head -c 64 /dev/urandom > ${key}
      chmod 0400 ${key}
    '';
  };
  postDisko =
    (
      if plaintextRootTest then
        ''
          # Install the encrypted-root generation onto an existing plaintext layout.
          # Only disposable test disks are reformatted here, never by the boot helper.
          machine.succeed("umount -R /mnt; cryptsetup close cryptroot")
          machine.succeed("wipefs -a /dev/disk/by-partlabel/disk-system-root; mkfs.btrfs -f /dev/disk/by-partlabel/disk-system-root")
          machine.succeed("mount /dev/disk/by-partlabel/disk-system-root /mnt; btrfs subvolume create /mnt/root /mnt/home /mnt/nix; umount /mnt")
          machine.succeed("mount -o subvol=root /dev/disk/by-partlabel/disk-system-root /mnt; mkdir -p /mnt/home /mnt/nix /mnt/boot /mnt/srv/data")
          machine.succeed("mount -o subvol=home /dev/disk/by-partlabel/disk-system-root /mnt/home; mount -o subvol=nix /dev/disk/by-partlabel/disk-system-root /mnt/nix")
          machine.succeed("mount /dev/disk/by-partlabel/disk-system-ESP /mnt/boot; mount /dev/mapper/lx-data /mnt/srv/data")
          machine.succeed("mkdir -p /mnt/home/admin; echo preserved > /mnt/home/admin/root-mode-marker")
        ''
      else
        ''
          # Fresh targets have no machine-id yet. Stage a real verified receipt before
          # the install hook, replacing only the private prompt with a synthetic value.
          machine.succeed("install -d -m 0755 /mnt/var/lib")
          machine.succeed("${pkgs.systemd}/bin/systemd-machine-id-setup --root=/mnt")
          machine.succeed("mkdir -p /mnt/nix/store; mount --bind /nix/store /mnt/nix/store; touch /mnt/etc/NIXOS")
          # cryptsetup resolves mapping type through udev state; a bare chroot reports
          # n/a even for LUKS2. Expose the installer metadata without granting writes.
          machine.succeed("mkdir -p /mnt/run/udev; mount --bind /run/udev /mnt/run/udev; mount -o remount,bind,ro /mnt/run/udev")
          stage_password = "import sys; sys.path.insert(0, '${repoRoot}'); from lx_administration.storage import boot_password as b; b.secret = lambda _: b'secretsecret'; b.prepare('/dev/disk/by-partlabel/disk-system-root')"
          machine.succeed("nixos-enter --root /mnt -- ${pkgs.coreutils}/bin/env PATH=${
            pkgs.lib.makeBinPath [
              pkgs.util-linux
              pkgs.cryptsetup
            ]
          } ${pkgs.python3}/bin/python3 -c " + shlex.quote(stage_password))
          machine.succeed("umount /mnt/nix/store")
          machine.succeed("install -d -m 0700 /mnt/etc/luks-keys; cp -p ${key} /mnt${key}")
        ''
    )
    + pkgs.lib.optionalString remoteUnlockTest ''
      machine.succeed("install -d -m 0700 /mnt/etc/luxnix/initrd-ssh; install -m 0600 /etc/test-initrd-host-key /mnt/etc/luxnix/initrd-ssh/ssh_host_ed25519_key")
    '';
  extraSystemConfig = { lib, pkgs, ... }: {
    imports = [ "${repoRoot}/modules/nixos/luxnix/operator-unlocked-storage" ];
    options = {
      luxnix.storage.loginAccess.enable = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
      luxnix.vault.server.managedTls.encryptedStorage = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
    };
    config = {
      # Boot LUKS enables Plymouth itself; match the fleet splash kernel parameters.
      boot.kernelParams = [
        "quiet"
        "splash"
      ];
      # Disko's generic test harness embeds a synthetic root key; this test must
      # actually exercise a console prompt instead.
      boot.initrd.secrets = lib.mkForce (
        lib.optionalAttrs remoteUnlockTest {
          "/etc/luxnix/initrd-ssh/ssh_host_ed25519_key" = null;
        }
      );
      luxnix.storage.operatorUnlocked = {
        enable = true;
        plaintextRootBridge = plaintextRootTest;
        autoStartProtectedServices = !deferStartupTest;
        guardedServices.writer = if plaintextRootTest then [ "/home" ] else [ "/srv/data" ];
        remoteUnlock = lib.mkIf remoteUnlockTest {
          enable = true;
          interface = "eth0";
          kernelModules = [
            "virtio_net"
            "e1000"
          ];
          address = "10.0.2.15/24";
          allowedSources = [ "10.0.2.2/32" ];
          authorizedKeys = [ (lib.fileContents (sshFixtures + "/id_ed25519.pub")) ];
        };
      };
      systemd.services.writer = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = "echo protected >> /srv/data/writes";
      };
      environment.systemPackages = [ pkgs.cryptsetup ];
      networking.useDHCP = false;
      specialisation.updated.configuration.environment.etc."storage-update-test".text = "updated";
    };
  };
  bootCommands =
    if plaintextRootTest then
      ""
    else if remoteUnlockTest then
      ''
        import os, select, shutil, subprocess, tempfile, time
        machine.wait_for_console_text("Please enter passphrase")
        machine.wait_for_console_text("Server listening on 10.0.2.15 port 2222")
        machine.forward_port(22444, 2222)
        with tempfile.TemporaryDirectory() as directory:
            identity = directory + "/operator"
            shutil.copyfile("${sshFixtures}/id_ed25519", identity)
            os.chmod(identity, 0o600)
            known = directory + "/known_hosts"
            with open(known, "w") as stream:
                stream.write("[127.0.0.1]:22444 " + open("${sshFixtures}/ssh_host_ed25519_key.pub").read())
            command = ["${pkgs.openssh}/bin/ssh", "-tt", "-p", "22444", "-i", identity,
                       "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + known,
                       "-o", "IdentitiesOnly=yes", "root@127.0.0.1", "touch /unauthorized-shell-command"]
            def enter_passphrase(value):
                with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT) as client:
                    assert client.stdout is not None
                    output = b""
                    deadline = time.monotonic() + 30
                    while b"(cryptroot):" not in output:
                        assert time.monotonic() < deadline, output.decode(errors="replace")
                        ready, _, _ = select.select([client.stdout], [], [], 1)
                        if ready:
                            chunk = os.read(client.stdout.fileno(), 4096)
                            assert chunk, output.decode(errors="replace")
                            output += chunk
                    assert b"This connection cannot run other commands" in output
                    client.communicate((value + "\n").encode(), timeout=30)
            # A failed disk passphrase leaves SSH available for another operator attempt.
            enter_passphrase("wrong-test-passphrase")
            time.sleep(3)
            enter_passphrase("secretsecret")
      ''
    else
      ''
        machine.wait_for_console_text("Please enter passphrase")
        machine.send_chars("secretsecret\n")
      '';
  extraTestScript =
    if plaintextRootTest then
      ''
        for attempt in range(2):
            machine.wait_for_unit("multi-user.target")
            machine.succeed("findmnt -no SOURCE / | grep /dev/mapper/cryptroot")
            machine.succeed("dmsetup table cryptroot | grep ' linear '")
            machine.succeed("grep -x preserved /home/admin/root-mode-marker")
            machine.fail("cryptsetup isLuks /dev/disk/by-partlabel/disk-system-root")
            machine.fail("luxnix-verify-boot-storage")
            machine.fail("systemctl start writer.service")
            machine.fail("systemctl is-active writer.service")
            assert "Booting plaintext root for migration" in machine.succeed("journalctl -b --no-pager")
            assert "Please enter passphrase" not in machine.get_console_log()
            if attempt == 0:
                machine.shutdown()
                machine.start()
      ''
    else
      pkgs.lib.optionalString mdraidTest ''
        machine.wait_for_unit("srv-data.mount")
        machine.succeed("test $(cat /sys/class/block/$(basename $(readlink -f /dev/md/application))/md/raid_disks) = 1")
        machine.succeed("cryptsetup isLuks --type luks2 /dev/md/application")
        machine.fail("cryptsetup isLuks /dev/disk/by-partlabel/disk-data-data")
      ''
      + ''
        def wait_for_writer():
            if ${if deferStartupTest then "True" else "False"}:
                machine.fail("systemctl is-active writer.service")
                machine.succeed("systemctl start writer.service")
            machine.wait_for_unit("writer.service")

        wait_for_writer()
        # The root passphrase must be answered on the Plymouth splash, not the bare console agent.
        boot_log = machine.succeed("journalctl -b _PID=1 -o cat --no-pager")
        assert "Started Forward Password Requests to Plymouth." in boot_log, boot_log
        assert "Started Dispatch Password Requests to Console." not in boot_log, boot_log
        machine.fail("test -e /unauthorized-shell-command")
        machine.succeed("luxnix-verify-boot-storage")
        receipt = machine.succeed("sha256sum /var/lib/luxnix-boot-passphrase/cryptroot.json")
        machine.succeed("luxnix-setup-root-encryption")
        machine.succeed("luxnix-setup-root-encryption --setup-password")
        assert machine.succeed("sha256sum /var/lib/luxnix-boot-passphrase/cryptroot.json") == receipt
        fingerprint = machine.succeed("sha256sum ${key}")
        machine.succeed("/run/current-system/bin/switch-to-configuration test")
        assert machine.succeed("sha256sum ${key}") == fingerprint
        machine.succeed("systemctl stop srv-data.mount")
        machine.fail("systemctl is-active writer.service")
        machine.succeed("systemctl stop systemd-cryptsetup@$(systemd-escape lx-data).service")
        machine.succeed("mv ${key} ${key}.saved")
        machine.fail("systemctl start writer.service")
        machine.fail("test -e /srv/data/writes")
        machine.succeed("mv ${key}.saved ${key}; systemctl reset-failed; systemctl start writer.service")
        machine.succeed("luxnix-verify-boot-storage")
        # A writable overlay on encrypted root lets the guest update its profile
        # without mutating the harness's shared read-only host store.
        machine.succeed("mkdir -p /run/store-lower /var/lib/test-store/upper /var/lib/test-store/work; mount --bind /nix/store /run/store-lower; mount -t overlay overlay -o lowerdir=/run/store-lower,upperdir=/var/lib/test-store/upper,workdir=/var/lib/test-store/work /nix/store")
        # The harness does not populate the guest store database. Publish the
        # already built closure as a generation; exercise the real boot switch below.
        machine.succeed("ln -s $(readlink -f /run/current-system/specialisation/updated) /nix/var/nix/profiles/system-2-link; ln -sfn system-2-link /nix/var/nix/profiles/system")
        machine.succeed("/nix/var/nix/profiles/system/bin/switch-to-configuration boot")
        machine.shutdown()
        machine.start()
        machine.wait_for_console_text("Please enter passphrase")
        machine.send_chars("secretsecret\n")
        wait_for_writer()
        assert machine.succeed("sha256sum ${key}") == fingerprint
        machine.succeed("test -f /etc/storage-update-test; luxnix-verify-boot-storage")
        machine.succeed("mv ${key} ${key}.saved")
        machine.shutdown()
        machine.start()
        machine.wait_for_console_text("Please enter passphrase")
        machine.send_chars("secretsecret\n")
        machine.wait_for_unit("multi-user.target")
        machine.fail("systemctl start writer.service")
        machine.fail("systemctl is-active writer.service")
        machine.fail("test -e /srv/data/writes")
        machine.succeed("mv ${key}.saved ${key}; systemctl reset-failed; systemctl start writer.service")
        machine.succeed("printf secretsecret > /run/test-root-key; printf recovery-test > /run/test-recovery-key; cryptsetup luksAddKey /dev/disk/by-partlabel/disk-system-root /run/test-recovery-key --key-file /run/test-root-key")
        machine.shutdown()
        machine.start()
        machine.wait_for_console_text("Please enter passphrase")
        machine.send_chars("recovery-test\n")
        wait_for_writer()
        machine.succeed("luxnix-verify-boot-storage")
      '';
}
