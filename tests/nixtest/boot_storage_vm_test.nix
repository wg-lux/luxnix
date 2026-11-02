# Destructive provisioning is confined to disposable QEMU disks and test keys.
{
  pkgs,
  disko,
  repoRoot,
  remoteUnlockTest ? false,
}:
let
  key = "/etc/luks-keys/lx-data.key";
  sshFixtures = pkgs.path + "/nixos/tests/initrd-network-ssh";
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
                content = {
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
            content = {
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
          };
        };
      };
    };
  };
in
disko.lib.testLib.makeDiskoTest {
  inherit pkgs;
  name = if remoteUnlockTest then "boot-storage-remote" else "boot-storage";
  disko-config = raw;
  enableOCR = true;
  extraInstallerConfig = { pkgs, ... }: {
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
  postDisko = ''
    machine.succeed("install -d -m 0700 /mnt/etc/luks-keys; cp -p ${key} /mnt${key}")
  ''
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
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.enable = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
    };
    config = {
      # Disko's generic test harness embeds a synthetic root key; this test must
      # actually exercise a console prompt instead.
      boot.initrd.secrets = lib.mkForce (
        lib.optionalAttrs remoteUnlockTest {
          "/etc/luxnix/initrd-ssh/ssh_host_ed25519_key" = null;
        }
      );
      luxnix.storage.operatorUnlocked = {
        enable = true;
        guardedServices.writer = [ "/srv/data" ];
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
    if remoteUnlockTest then
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
  extraTestScript = ''
    machine.wait_for_unit("writer.service")
    machine.fail("test -e /unauthorized-shell-command")
    machine.succeed("luxnix-verify-boot-storage")
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
    machine.wait_for_unit("writer.service")
    assert machine.succeed("sha256sum ${key}") == fingerprint
    machine.succeed("test -f /etc/storage-update-test; luxnix-verify-boot-storage")
    machine.succeed("mv ${key} ${key}.saved")
    machine.shutdown()
    machine.start()
    machine.wait_for_console_text("Please enter passphrase")
    machine.send_chars("secretsecret\n")
    machine.wait_for_unit("multi-user.target")
    machine.fail("systemctl is-active writer.service")
    machine.fail("test -e /srv/data/writes")
    machine.succeed("mv ${key}.saved ${key}; systemctl reset-failed; systemctl start writer.service")
    machine.succeed("printf secretsecret > /run/test-root-key; printf recovery-test > /run/test-recovery-key; cryptsetup luksAddKey /dev/disk/by-partlabel/disk-system-root /run/test-recovery-key --key-file /run/test-root-key")
    machine.shutdown()
    machine.start()
    machine.wait_for_console_text("Please enter passphrase")
    machine.send_chars("recovery-test\n")
    machine.wait_for_unit("writer.service")
    machine.succeed("luxnix-verify-boot-storage")
  '';
}
