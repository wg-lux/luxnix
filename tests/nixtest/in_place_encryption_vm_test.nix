# Start from a plaintext Btrfs root holding real containers, encrypt it in place, cut
# the power mid-conversion, resume, move the container data onto the encrypted root,
# cold boot, use the data, then retire the containers. Disposable QEMU disks and
# synthetic keys only.
{
  pkgs,
  disko,
  repoRoot,
}:
let
  rootPartition = "/dev/disk/by-partlabel/disk-system-root";
  swapPartition = "/dev/disk/by-partlabel/disk-system-oldswap";
  subvolumeOptions = name: [ "subvol=${name}" ];
  # Mirrors the evaluated plan: config.in_place and config.mounts.
  driver = pkgs.writeText "in-place-driver.py" ''
    import sys
    sys.path.insert(0, "${repoRoot}")
    from lx_administration.storage import in_place as p

    layout = {
        "root_device": "${rootPartition}",
        "swap_partitions": ["${swapPartition}"],
        "containers": [
            {"name": "luxnix-secrets", "container": "/var/lib/luxnix-secrets.luks",
             "mountPoint": "/var/lib/luxnix-secrets", "fsType": "ext4"},
            {"name": "luxnix-app-storage", "container": "/var/lib/luxnix-app-storage.luks",
             "mountPoint": "/var/lib/luxnix-app-storage", "fsType": "ext4"},
        ],
        "binds": {
            "/etc/secrets": {"volume": "luxnix-secrets", "directory": "host-secrets"},
            "/etc/secrets/vault": {"volume": "luxnix-secrets", "directory": "managed-secrets"},
            "/var/lib/lx-annotate": {"volume": "luxnix-app-storage", "directory": "application"},
        },
    }
    mounts = {
        "/": {"device": "/dev/mapper/cryptroot", "fsType": "btrfs", "options": ["subvol=root"]},
        "/nix": {"device": "/dev/mapper/cryptroot", "fsType": "btrfs", "options": ["subvol=nix"]},
        "/home": {"device": "/dev/mapper/cryptroot", "fsType": "btrfs", "options": ["subvol=home"]},
        "/boot": {"device": "/dev/disk/by-partlabel/disk-system-ESP", "fsType": "vfat", "options": []},
    }
    command = sys.argv[1]
    if command == "state":
        print(p.root_state(layout["root_device"]))
    elif command == "convert":
        passphrases = {
            "luxnix-secrets": b"secrets-recovery",
            "luxnix-app-storage": sys.argv[2].encode(),
        }
        print(p.convert(layout, mounts, root_passphrase=b"secretsecret",
                        container_passphrases=passphrases))
    elif command == "retire":
        print(p.retire_containers(layout["containers"], layout["binds"]))
    elif command == "bad-passphrase":
        try:
            p.check_passphrase(b"secretsecretyz")
        except p.InPlaceError:
            print("refused")
  '';
  installerPackages = [
    pkgs.btrfs-progs
    pkgs.cryptsetup
    pkgs.e2fsprogs
    pkgs.procps
    pkgs.python3
    pkgs.util-linux
  ];
  raw = {
    disko.devices.disk.system = {
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
          # An old plaintext swap partition the configuration no longer uses.
          oldswap = {
            size = "64M";
            type = "8200";
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
                type = "btrfs";
                extraArgs = [ "-f" ];
                subvolumes = {
                  root = {
                    mountpoint = "/";
                    mountOptions = subvolumeOptions "root";
                  };
                  nix = {
                    mountpoint = "/nix";
                    mountOptions = subvolumeOptions "nix";
                  };
                  home = {
                    mountpoint = "/home";
                    mountOptions = subvolumeOptions "home";
                  };
                };
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
  name = "boot-storage-in-place";
  disko-config = raw;
  enableOCR = true;
  extraInstallerConfig = {
    environment.systemPackages = installerPackages;
  };
  postDisko = ''
    in_place = "python3 ${driver} "

    # Replace what the harness formatted with the plaintext host we migrate from.
    machine.succeed("umount -R /mnt; cryptsetup close cryptroot")
    machine.succeed("wipefs -a ${rootPartition}; mkswap ${swapPartition}")
    machine.succeed("mkfs.btrfs -f -L nixos ${rootPartition}")
    machine.succeed("mkdir -p /plain; mount -o subvolid=5 ${rootPartition} /plain")
    machine.succeed("cd /plain; btrfs subvolume create root nix home")
    machine.succeed("mkdir -p /plain/root/var/lib /plain/root/etc /plain/home/admin")
    # What the old root held beneath a mount point must not be lost either.
    machine.succeed("mkdir -p /plain/root/var/lib/lx-annotate; echo stale > /plain/root/var/lib/lx-annotate/stale")
    machine.succeed("${pkgs.systemd}/bin/systemd-machine-id-setup --root=/plain/root")
    # Enough incompressible data that the conversion is still running at the power cut.
    machine.succeed("head -c 1200M /dev/urandom > /plain/home/admin/data.bin")
    machine.succeed("echo PLAINTEXT-MARKER-HOME-7f3a > /plain/home/admin/marker")

    def make_container(name, passphrase, directories):
        path = "/plain/root/var/lib/" + name + ".luks"
        machine.succeed("truncate -s 96M " + path)
        machine.succeed(f"printf %s {passphrase} | cryptsetup luksFormat --type luks2 --batch-mode --pbkdf-memory 32768 --key-file - {path}")
        machine.succeed(f"printf %s {passphrase} | cryptsetup open --key-file - {path} {name}")
        machine.succeed(f"mkfs.ext4 -q /dev/mapper/{name}")
        machine.succeed(f"mkdir -p /c; mount /dev/mapper/{name} /c")
        for directory in directories:
            machine.succeed(f"mkdir -p /c/{directory}")
        return path

    def close_container(name):
        machine.succeed(f"umount /c; cryptsetup close {name}")

    make_container("luxnix-secrets", "secrets-recovery", ["host-secrets", "managed-secrets"])
    machine.succeed("echo host-issued-salt-value > /c/managed-secrets/lx_annotate_identity_active")
    close_container("luxnix-secrets")
    make_container("luxnix-app-storage", "app-recovery", ["application/data"])
    machine.succeed("echo proprietary-record > /c/application/data/record")
    close_container("luxnix-app-storage")
    machine.succeed("sha256sum /plain/home/admin/data.bin | cut -d' ' -f1 > /tmp/data.sha")
    data_sha = machine.succeed("cat /tmp/data.sha").strip()
    machine.succeed("umount /plain; sync")

    # An unsafe passphrase is refused, and so is a wrong container passphrase,
    # both before a single byte of the disk changes.
    assert machine.succeed(in_place + "bad-passphrase").strip() == "refused"
    machine.fail(in_place + "convert wrong-passphrase")
    assert machine.succeed(in_place + "state").strip() == "plaintext"
    machine.succeed("blkid -p -o value -s TYPE ${rootPartition} | grep -x btrfs")

    # Cut the power mid-conversion, then resume from the header on a fresh boot.
    machine.succeed("(" + in_place + "convert app-recovery > /tmp/first.log 2>&1 &) ; true")
    machine.wait_until_succeeds("cryptsetup isLuks ${rootPartition}", timeout=300)
    machine.succeed("sleep 1")
    machine.crash()
    machine.start()
    machine.wait_for_unit("multi-user.target")
    assert machine.succeed(in_place + "state").strip() == "encrypting", "the power cut missed the conversion"
    machine.succeed("cryptsetup isLuks ${rootPartition}")

    machine.succeed(in_place + "convert app-recovery")
    assert machine.succeed(in_place + "state").strip() == "encrypted"

    # The real data survived and the container data now lives on the encrypted root.
    assert machine.succeed("sha256sum /mnt/home/admin/data.bin | cut -d' ' -f1").strip() == data_sha
    machine.succeed("grep -x PLAINTEXT-MARKER-HOME-7f3a /mnt/home/admin/marker")
    machine.succeed("grep -x host-issued-salt-value /mnt/etc/secrets/vault/lx_annotate_identity_active")
    machine.succeed("grep -x proprietary-record /mnt/var/lib/lx-annotate/data/record")
    machine.succeed("grep -x stale /mnt/var/lib/lx-annotate.pre-consolidation/stale")
    machine.fail("mountpoint -q /mnt/etc/secrets/vault")
    machine.fail("test -e /dev/mapper/luxnix-consolidate-luxnix-secrets")
    # Containers are untouched until they are retired after acceptance.
    machine.succeed("printf %s secrets-recovery | cryptsetup open --test-passphrase --key-file - /mnt/var/lib/luxnix-secrets.luks")
    machine.fail("blkid -p -o value -s TYPE ${swapPartition} | grep -x swap")

    # Running it again must not disturb a finished conversion's data.
    machine.fail(in_place + "convert app-recovery")
    machine.succeed("grep -x proprietary-record /mnt/var/lib/lx-annotate/data/record")

    machine.succeed("mkdir -p /mnt/nix/store; mount --bind /nix/store /mnt/nix/store; touch /mnt/etc/NIXOS")
    # A bare chroot needs udev state to resolve the mapping type; never writable.
    machine.succeed("mkdir -p /mnt/run/udev; mount --bind /run/udev /mnt/run/udev; mount -o remount,bind,ro /mnt/run/udev")
    machine.succeed("umount /mnt/nix/store")
  '';
  extraSystemConfig =
    { lib, pkgs, ... }:
    {
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

        boot.kernelParams = [
          "quiet"
          "splash"
        ];
        # Disko's harness embeds a synthetic root key; this test needs the real prompt.
        boot.initrd.secrets = lib.mkForce { };
        # Mirror gc-09: no discovered swap, and resume= names the label that moves
        # from the plaintext partition onto the mapper during the conversion.
        swapDevices = lib.mkForce [ ];
        systemd.generators.systemd-gpt-auto-generator = "/dev/null";
        boot.resumeDevice = "/dev/disk/by-label/nixos";
        # The driver reads the console by line and the prompt has no line ending,
        # so without this it only sees the prompt if later output happens to follow.
        # Do not pass wait_for_console_text a timeout: it then reads one line per second.
        boot.initrd.systemd.services.console-line-flush = {
          wantedBy = [ "initrd.target" ];
          before = [ "initrd-switch-root.target" ];
          conflicts = [ "initrd-switch-root.target" ];
          unitConfig.DefaultDependencies = false;
          script = "while :; do echo > /dev/console; /bin/sleep 1; done";
        };
        luxnix.storage.operatorUnlocked = {
          enable = true;
          guardedServices.application = [
            "/etc/secrets/vault"
            "/var/lib/lx-annotate"
          ];
        };
        # Stands in for lx-annotate: it needs the salt and works inside encrypted storage.
        systemd.services.application = {
          wantedBy = [ "multi-user.target" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
          };
          script = ''
            grep -x host-issued-salt-value /etc/secrets/vault/lx_annotate_identity_active
            grep -x proprietary-record /var/lib/lx-annotate/data/record
            echo started >> /var/lib/lx-annotate/data/starts
          '';
        };
        networking.useDHCP = false;
        environment.etc."in-place-driver.py".source = driver;
        environment.systemPackages = [
          pkgs.python3
          pkgs.btrfs-progs
        ];
      };
    };
  bootCommands = ''
    machine.wait_for_console_text("Please enter passphrase")
    machine.send_chars("secretsecret\n")
  '';
  extraTestScript = ''
    def unlock():
        machine.wait_for_console_text("Please enter passphrase")
        machine.send_chars("secretsecret\n")

    # Only the root prompts, and the application runs directly on encrypted root.
    machine.wait_for_unit("application.service")
    machine.succeed("grep -c started /var/lib/lx-annotate/data/starts")
    machine.succeed("cryptsetup status cryptroot | grep -i 'type:.*LUKS2'")
    machine.fail("test -e /dev/mapper/luxnix-secrets")
    machine.fail("mountpoint -q /etc/secrets/vault")
    machine.succeed("findmnt -no SOURCE --target /etc/secrets/vault | grep cryptroot")
    machine.succeed("findmnt -no SOURCE --target /var/lib/lx-annotate | grep cryptroot")
    machine.succeed("luxnix-verify-boot-storage")
    machine.succeed("luxnix-setup-root-encryption --setup-password")
    machine.succeed("cryptsetup --version")
    # The erased plaintext swap stays out of use.
    assert machine.succeed("swapon --show --noheadings").strip() == ""
    print(machine.succeed("systemctl --failed --no-legend --plain || true"))

    # The data survived the whole path, and is no longer readable on the raw disk.
    machine.succeed("grep -x PLAINTEXT-MARKER-HOME-7f3a /home/admin/marker")
    machine.fail("grep -qa PLAINTEXT-MARKER-HOME-7f3a /dev/vda")

    # A second cold boot behaves the same.
    machine.shutdown()
    machine.start()
    unlock()
    machine.wait_for_unit("application.service")
    assert int(machine.succeed("grep -c started /var/lib/lx-annotate/data/starts").strip()) == 2

    # Retiring deletes only the container files; everything keeps working after it.
    machine.succeed("test -f /var/lib/luxnix-secrets.luks; test -f /var/lib/luxnix-app-storage.luks")
    machine.succeed("python3 /etc/in-place-driver.py retire")
    machine.fail("test -e /var/lib/luxnix-secrets.luks")
    machine.fail("test -e /var/lib/luxnix-app-storage.luks")
    machine.succeed("grep -x host-issued-salt-value /etc/secrets/vault/lx_annotate_identity_active")
    machine.shutdown()
    machine.start()
    unlock()
    machine.wait_for_unit("application.service")
    assert int(machine.succeed("grep -c started /var/lib/lx-annotate/data/starts").strip()) == 3
    machine.succeed("luxnix-verify-boot-storage")
  '';
}
