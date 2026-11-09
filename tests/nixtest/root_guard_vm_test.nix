# Runs the real preflight and recovery classifier against a disposable QEMU disk.
{
  pkgs,
  repoRoot,
}:
let
  source = pkgs.runCommand "root-guard-source" { } ''
    mkdir -p "$out"
    cp ${repoRoot + "/lx_administration/storage/root_guard.py"} "$out/root_guard.py"
    cp ${repoRoot + "/lx_administration/storage/root_recovery.py"} "$out/root_recovery.py"
    cp ${repoRoot + "/lx_administration/storage/boot_password.py"} "$out/boot_password.py"
    cp ${repoRoot + "/lx_administration/storage/boot.py"} "$out/boot.py"
    cp ${repoRoot + "/lx_administration/storage/cutover.py"} "$out/cutover.py"
    cp ${repoRoot + "/lx_administration/secret_storage.py"} "$out/secret_storage.py"
  '';
  spec =
    {
      layout,
      disk ? "/dev/disk/by-id/test-root",
    }:
    let
      encrypted = layout == "boot-luks";
      device = if encrypted then "/dev/mapper/cryptroot" else "/dev/disk/by-partlabel/nixos_root";
    in
    pkgs.writeText "${layout}-spec.json" (
      builtins.toJSON {
        version = 1;
        host = "machine";
        inherit layout;
        root = {
          partition = "/dev/disk/by-partlabel/nixos_root";
          fsType = "btrfs";
          inherit disk;
          mapping = if encrypted then "cryptroot" else null;
          expected_luks_uuid = null;
          require_persistent_disk = false;
        };
        mounts = {
          "/" = {
            inherit device;
            fsType = "btrfs";
            subvolume = "root";
          };
          "/home" = {
            inherit device;
            fsType = "btrfs";
            subvolume = "home";
          };
        };
        initrd = {
          systemd = true;
          unlocks_root = encrypted;
          plaintext_bridge = false;
        };
        bootloader = {
          kind = "none";
          esp = "/mnt/boot";
          limit = 5;
        };
      }
    );
  legacy = spec { layout = "legacy-containers"; };
  luks = spec { layout = "boot-luks"; };
  wrongDisk = spec {
    layout = "boot-luks";
    disk = "/dev/disk/by-id/test-other";
  };
in
pkgs.testers.runNixOSTest {
  name = "root-guard";
  # The generated switch entry point on a real, incompatible generation.
  nodes.deployed =
    { lib, ... }:
    {
      imports = [ (repoRoot + "/modules/nixos/luxnix/operator-unlocked-storage/root-guard.nix") ];
      options.luxnix.storage.operatorUnlocked = {
        enable = lib.mkEnableOption "stub";
        layout = lib.mkOption {
          type = lib.types.str;
          default = "legacy-containers";
        };
      };
      config = {
        system.switch.enable = true;
        environment.etc.machine-id.text = "11111111111111111111111111111111";
        luxnix.storage.operatorUnlocked = {
          enable = true;
          rootIdentity.disk = "/dev/vda";
        };
        specialisation.candidate.configuration = {
          luxnix.storage.operatorUnlocked.layout = lib.mkForce "boot-luks";
          # qemu-vm clears LUKS devices with mkVMOverride; this generation never boots.
          boot.initrd.luks.devices = lib.mkOverride 5 { cryptroot.device = "/dev/vda"; };
          boot.initrd.systemd.enable = true;
        };
      };
    };
  nodes.machine =
    { pkgs, ... }:
    {
      virtualisation.emptyDiskImages = [
        2048
        512
      ];
      environment.systemPackages = [
        pkgs.cryptsetup
        pkgs.btrfs-progs
        pkgs.gptfdisk
        pkgs.python3
      ];
    };
  testScript = ''
    guard = "python3 ${source}/root_guard.py verify --system /nix/store/${"a"}-nixos-system-x --action dry-activate --root /mnt --spec "
    recover = "python3 ${source}/root_recovery.py classify --partition /dev/disk/by-partlabel/nixos_root"
    mounted_state = (
        "python3 -c 'import sys; from pathlib import Path; "
        "sys.path.insert(0,\"${source}\"); import root_recovery; "
        "print(root_recovery.mounted_root_state(Path(\"/mnt\")))'"
    )
    partition = "/dev/disk/by-partlabel/nixos_root"

    def layout(device):
        machine.succeed(f"mount -t btrfs {device} /run/top")
        machine.succeed("btrfs subvolume create /run/top/root /run/top/home; umount /run/top")
        machine.succeed(f"mount -o subvol=root {device} /mnt; mkdir -p /mnt/home")
        machine.succeed(f"mount -o subvol=home {device} /mnt/home")

    deployed.wait_for_unit("multi-user.target")
    candidate = "/run/current-system/specialisation/candidate/bin/switch-to-configuration"
    profile = "readlink /nix/var/nix/profiles/system"
    deployed.succeed("mkdir -p /nix/var/nix/profiles; ln -s $(readlink -f /run/current-system) /nix/var/nix/profiles/system-1-link; ln -s system-1-link /nix/var/nix/profiles/system")
    before = deployed.succeed(profile)
    with subtest("generated entry point refuses an incompatible generation"):
        for action in ("boot", "switch"):
            output = deployed.fail(f"{candidate} {action} 2>&1")
            assert "root-not-luks" in output, output
    with subtest("NIXOS_NO_CHECK does not skip the root storage check"):
        output = deployed.fail(f"NIXOS_NO_CHECK=1 {candidate} boot 2>&1")
        assert "root-not-luks" in output, output
        assert deployed.succeed(profile) == before
        deployed.succeed("grep no-check-environment /var/lib/luxnix/root-guard-audit.jsonl")
    with subtest("sudo does not forward the bypass variable"):
        deployed.succeed("grep -F 'env_keep-=NIXOS_NO_CHECK' /etc/sudoers")

    machine.wait_for_unit("multi-user.target")
    machine.succeed("mkdir -p /run/top /mnt /dev/disk/by-id")
    machine.succeed("ln -s /dev/vdb /dev/disk/by-id/test-root; ln -s /dev/vdc /dev/disk/by-id/test-other")
    machine.succeed("sgdisk -n1:0:0 -c1:nixos_root /dev/vdb; udevadm settle")

    with subtest("plaintext root matches legacy-containers"):
        machine.succeed(f"mkfs.btrfs -f {partition}; udevadm settle")
        layout(partition)
        machine.succeed(guard + "${legacy}")
        machine.succeed(guard + "${legacy}")  # repeating changes nothing
        assert machine.succeed(mounted_state).strip() == "plaintext"

    with subtest("boot-luks on plaintext root is refused"):
        output = machine.fail(guard + "${luks} 2>&1")
        assert "root-not-luks" in output, output

    with subtest("recovery classifies plaintext"):
        assert "plaintext" in machine.succeed(recover)

    machine.succeed("umount -R /mnt")

    with subtest("LUKS2 root matches boot-luks"):
        machine.succeed(f"echo -n secretsecret | cryptsetup luksFormat --type luks2 --batch-mode --pbkdf pbkdf2 --pbkdf-force-iterations 1000 {partition} -")
        machine.succeed(f"echo -n secretsecret | cryptsetup open --type luks2 {partition} cryptroot -; udevadm settle")
        machine.succeed("mkfs.btrfs -f /dev/mapper/cryptroot; udevadm settle")
        layout("/dev/mapper/cryptroot")
        machine.succeed(guard + "${luks}")
        assert machine.succeed(mounted_state).strip() == "encrypted"

    with subtest("plaintext generation on encrypted root is refused"):
        output = machine.fail(guard + "${legacy} 2>&1")
        assert "root-is-luks" in output, output

    with subtest("incorrect disk identity is refused"):
        output = machine.fail(guard + "${wrongDisk} 2>&1")
        assert "partition-identity" in output, output

    with subtest("recovery classifies encrypted"):
        assert "encrypted" in machine.succeed(recover)

    with subtest("missing cryptroot is refused"):
        machine.succeed("umount -R /mnt; cryptsetup close cryptroot; udevadm settle; mkdir -p /mnt/home")
        machine.succeed("mount -t tmpfs none /mnt")
        assert machine.succeed(mounted_state).strip() == "unknown"
        output = machine.fail(guard + "${luks} 2>&1")
        assert "mapping-missing" in output, output
        machine.succeed("umount /mnt")

    with subtest("interrupted encryption is classified and refused"):
        machine.succeed(f"cryptsetup erase --batch-mode {partition}; wipefs -a {partition}; udevadm settle")
        machine.succeed(f"mkfs.btrfs -f --byte-count 1G {partition}; udevadm settle")
        machine.succeed(f"echo -n secretsecret | cryptsetup reencrypt --encrypt --type luks2 --init-only --reduce-device-size 32M --batch-mode --pbkdf pbkdf2 --pbkdf-force-iterations 1000 {partition} -")
        assert "encrypting" in machine.succeed(recover)
        output = machine.fail(guard + "${luks} 2>&1")
        assert "root-reencrypting" in output or "mapping-missing" in output, output
  '';
}
