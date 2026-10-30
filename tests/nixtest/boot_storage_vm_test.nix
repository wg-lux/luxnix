# Destructive provisioning is confined to disposable QEMU disks and test keys.
{
  pkgs,
  disko,
  repoRoot,
}:
let
  key = "/etc/luks-keys/lx-data.key";
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
  name = "boot-storage";
  disko-config = raw;
  enableOCR = true;
  extraInstallerConfig = { pkgs, ... }: {
    system.activationScripts.testSecondaryKey = ''
      install -d -m 0700 /etc/luks-keys
      ${pkgs.coreutils}/bin/head -c 64 /dev/urandom > ${key}
      chmod 0400 ${key}
    '';
  };
  postDisko = ''
    machine.succeed("install -d -m 0700 /mnt/etc/luks-keys; cp -p ${key} /mnt${key}")
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
      boot.initrd.secrets = lib.mkForce { };
      luxnix.storage.operatorUnlocked = {
        enable = true;
        guardedServices.writer = [ "/srv/data" ];
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
  bootCommands = ''
    machine.wait_for_console_text("Please enter passphrase")
    machine.send_chars("secretsecret\n")
  '';
  extraTestScript = ''
    machine.wait_for_unit("writer.service")
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
