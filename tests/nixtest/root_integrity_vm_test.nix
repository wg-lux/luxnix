# Disposable prototype: unsigned UKI is a trusted fixture, not Secure Boot evidence.
{ repoRoot, ... }:
{ hostPkgs, ... }:
{
  name = "root-integrity";
  defaults =
    {
      config,
      lib,
      modulesPath,
      pkgs,
      ...
    }:
    let
      ids = config.image.repart.verityStore.partitionIds;
      sentinel = pkgs.writeShellScript "synthetic-release" ''
        set -eu
        test "$(cat /etc/release-policy)" = approved
        mkdir -p /run/root-integrity
        echo synthetic-release > /run/root-integrity/released
        echo ROOT_INTEGRITY_RELEASED > /dev/ttyS0
      '';
    in
    {
      imports = [ (modulesPath + "/image/repart.nix") ];
      fileSystems."/" = {
        fsType = "tmpfs";
        options = [ "mode=0755" ];
      };
      image.repart = {
        name = "root-integrity";
        verityStore = {
          enable = true;
          ukiPath = "/EFI/BOOT/BOOT${lib.toUpper config.nixpkgs.hostPlatform.efiArch}.EFI";
        };
        partitions.${ids.store}.repartConfig = {
          Format = lib.mkForce "ext4";
          Minimize = lib.mkForce "guess";
          SizeMinBytes = "4G";
        };
        partitions.${ids.esp}.repartConfig = {
          Type = "esp";
          Format = "vfat";
          SizeMinBytes = "96M";
        };
      };
      virtualisation = {
        fileSystems = lib.mkVMOverride { };
        directBoot.enable = false;
        mountHostNixStore = false;
        useEFIBoot = true;
        memorySize = 2048;
      };
      boot = {
        loader.grub.enable = false;
        initrd.systemd.enable = true;
      };
      system = {
        image.id = "root-integrity-test";
        stateVersion = "26.05";
        activationScripts.usrbinenv = lib.mkForce "";
      };
      environment.systemPackages = [
        pkgs.openbao
        pkgs.cryptsetup
      ];
      environment.etc = {
        "release-policy".text = "approved";
        "luxnix-openbao-local.py".source = repoRoot + "/lx_administration/storage/openbao_local.py";
      };
      systemd.services.synthetic-release = {
        wantedBy = [ "multi-user.target" ];
        after = [ "local-fs.target" ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = sentinel;
          RemainAfterExit = true;
        };
      };
    };
  nodes.machine = { };
  testScript = { nodes, ... }: ''
    import os
    import json
    import re
    import struct
    import subprocess
    import tempfile
    import time

    def wait_serial(pattern, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if re.search(pattern, machine.get_console_log(), re.IGNORECASE):
                return
            time.sleep(0.5)
        raise AssertionError(f"console did not contain {pattern!r}")

    image = "${nodes.machine.system.build.image}/${nodes.machine.image.filePath}"
    qemu = "${nodes.machine.virtualisation.qemu.package}/bin/"
    disks = []

    def fresh_disk():
        disk = tempfile.NamedTemporaryFile()
        disks.append(disk)
        subprocess.run([
            qemu + "qemu-img", "create", "-f", "qcow2",
            "-b", image, "-F", "raw", disk.name,
        ], check=True)
        os.environ["NIX_DISK_IMAGE"] = disk.name
        return disk.name

    def write_disk(disk, command):
        subprocess.run([qemu + "qemu-io", "-f", "qcow2", "-c", command, disk], check=True)

    def reject_boot(block_kind):
        machine.start()
        wait_serial(rf"device-mapper: verity: .*{block_kind} block [0-9]+ is corrupted")
        time.sleep(15)
        assert "ROOT_INTEGRITY_RELEASED" not in machine.get_console_log()
        machine.crash()

    disk = fresh_disk()
    machine.start(allow_reboot=True)
    wait_serial("ROOT_INTEGRITY_RELEASED")
    machine.wait_for_unit("multi-user.target", timeout=180)
    machine.wait_for_unit("synthetic-release.service", timeout=180)
    machine.succeed("test -f /run/root-integrity/released")
    machine.succeed("dmsetup info --target verity usr | grep ACTIVE")
    machine.succeed("findmnt -n -o SOURCE /nix/store | grep -E '^/dev/mapper/usr'")
    machine.succeed("findmnt -n -o FSTYPE /nix/store | grep -x ext4")
    machine.succeed("findmnt -n -o OPTIONS /nix/store | grep -E '(^|,)ro(,|$)'")
    machine.succeed("findmnt -n -o FSTYPE / | grep -x tmpfs")
    machine.fail("touch /nix/store/unauthorized")
    machine.succeed("rm /etc/release-policy; echo changed > /etc/release-policy; mkdir -p /var/lib/root-integrity; touch /var/lib/root-integrity/override")
    machine.succeed("rm /run/root-integrity/released")
    machine.fail("systemctl restart synthetic-release.service")
    machine.succeed("test ! -e /run/root-integrity/released")
    machine.reboot()
    machine.wait_for_unit("multi-user.target", timeout=180)
    machine.wait_for_unit("synthetic-release.service", timeout=180)
    machine.succeed("test -f /run/root-integrity/released; test \"$(cat /etc/release-policy)\" = approved; test ! -e /var/lib/root-integrity/override")

    # Exercise an actual writable unit/executable override before proving that
    # reconstruction of /etc and the tmpfs root removes it on the next boot.
    machine.fail("mkdir -p /etc/systemd/system/synthetic-release.service.d")
    machine.succeed("cp -rL /etc/systemd/system /run/root-integrity-units; chmod -R u+w /run/root-integrity-units; rm /etc/systemd/system; mv /run/root-integrity-units /etc/systemd/system")
    machine.succeed("mkdir -p /etc/systemd/system/synthetic-release.service.d /var/lib/root-integrity-bin")
    machine.succeed("printf '#!/bin/sh\\necho ROOT_INTEGRITY_OVERRIDE > /dev/ttyS0\\n' > /var/lib/root-integrity-bin/release-override; chmod +x /var/lib/root-integrity-bin/release-override")
    machine.succeed("printf '[Service]\\nExecStart=\\nExecStart=/var/lib/root-integrity-bin/release-override\\nEnvironment=ROOT_INTEGRITY_OVERRIDE=1\\n' > /etc/systemd/system/synthetic-release.service.d/override.conf")
    machine.succeed("systemctl daemon-reload; systemctl restart synthetic-release.service")
    wait_serial("ROOT_INTEGRITY_OVERRIDE")
    previous_console = len(machine.get_console_log())
    machine.reboot()
    machine.wait_for_unit("synthetic-release.service", timeout=180)
    machine.succeed("test -f /run/root-integrity/released; test ! -e /var/lib/root-integrity-bin/release-override; test ! -e /etc/systemd/system/synthetic-release.service.d/override.conf")
    machine.succeed("! systemctl show synthetic-release.service -p Environment | grep ROOT_INTEGRITY_OVERRIDE")
    assert "ROOT_INTEGRITY_OVERRIDE" not in machine.get_console_log()[previous_console:]
    machine.shutdown()

    partitions = json.load(open("${nodes.machine.system.build.image}/repart-output.json"))
    store = next(p for p in partitions if p["label"] == "store")
    hashes = next(p for p in partitions if p["label"] == "store-verity")

    with subtest("required data block corruption"):
        # ext4 superblock is required at mount, so this block must be read.
        disk = fresh_disk()
        write_disk(disk, f"write -P 0 {store['offset'] + 1024} 512")
        reject_boot("data")

    with subtest("hash tree corruption"):
        # Preserve the verity header, corrupt the first tree block, and require
        # a kernel integrity failure rather than counting a boot timeout.
        with open(image, "rb") as source:
            source.seek(hashes["offset"])
            header = source.read(512)
        assert header[:8] == b"verity" + bytes(2)
        data_block_size, hash_block_size = struct.unpack_from("<II", header, 64)
        assert data_block_size >= 512 and hash_block_size >= 512
        disk = fresh_disk()
        write_disk(disk, f"write -P 0 {hashes['offset'] + hash_block_size} {hash_block_size}")
        reject_boot("metadata")

    with subtest("substituted filesystem with original root hash"):
        # A newly formatted filesystem replaces the entire data partition;
        # the original hash tree, UKI and GPT identities remain unchanged.
        with tempfile.NamedTemporaryFile() as replacement:
            replacement.truncate(64 * 1024 * 1024)
            subprocess.run([
                "${hostPkgs.e2fsprogs}/bin/mkfs.ext4", "-F", replacement.name,
            ], check=True)
            disk = fresh_disk()
            chunk = 1024 * 1024 * 1024
            for offset in range(0, store["raw_size"], chunk):
                length = min(chunk, store["raw_size"] - offset)
                write_disk(disk, f"write -z {store['offset'] + offset} {length}")
            write_disk(disk, f"write -s {replacement.name} {store['offset']} {64 * 1024 * 1024}")
        reject_boot("data")

    with subtest("explicit recovery to original verified image"):
        fresh_disk()
        machine.start()
        machine.wait_for_unit("synthetic-release.service", timeout=180)
        machine.succeed("test -f /run/root-integrity/released; dmsetup info --target verity usr | grep ACTIVE")
        machine.shutdown()
  '';
}
