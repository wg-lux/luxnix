# Exercise the shipped CLI on disposable disks through UEFI boot and PAM login.
{
  pkgs,
  disko,
  repoRoot,
  multidisk ? false,
}:
let
  inherit (pkgs) lib;
  uuid = "12345678-1234-1234-1234-123456789012";
  device = "/dev/disk/by-id/virtio-fresh-target";
  python = pkgs.python312.withPackages (p: [
    p.pexpect
    p.pyyaml
    p.cryptography
  ]);
  hash = pkgs.runCommand "fresh-test-hash" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    printf 'vm-password' | openssl passwd -6 -stdin > "$out"
  '';
  layout =
    (import ../../systems/x86_64-linux/encrypted-layout.nix {
      inherit lib;
      config.luxnix.storage.operatorUnlocked = {
        enable = true;
        layout = "boot-luks";
      };
    })
      {
        disko.devices.disk =
          (lib.optionalAttrs multidisk {
            data = {
              type = "disk";
              device = "/dev/disk/by-id/virtio-fresh-data";
              content = {
                type = "gpt";
                partitions.payload = {
                  size = "100%";
                  content = {
                    type = "btrfs";
                    subvolumes.application.mountpoint = "/var/lib/lx-annotate";
                  };
                };
              };
            };
          })
          // {
            system = {
              type = "disk";
              inherit device;
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
                      type = "btrfs";
                      subvolumes.root.mountpoint = "/";
                    };
                  };
                };
              };
            };
          };
      };
  target = import (pkgs.path + "/nixos/lib/eval-config.nix") {
    system = pkgs.stdenv.hostPlatform.system;
    modules = [
      disko.nixosModules.disko
      layout
      ({ modulesPath, ... }: {
        imports = [
          (modulesPath + "/testing/test-instrumentation.nix")
          (modulesPath + "/profiles/qemu-guest.nix")
        ];
        documentation.enable = false;
        networking.hostName = "fresh-test";
        system.stateVersion = "26.05";
        boot = {
          loader.systemd-boot.enable = true;
          loader.efi.canTouchEfiVariables = false;
          initrd.systemd.enable = true;
          kernelParams = [ "console=ttyS0" ];
        };
        environment.etc.crypttab.text = lib.mkIf multidisk "luxnix-app-storage /dev/disk/by-partlabel/disk-data-payload /etc/luks-keys/luxnix-app-storage.key luks\n";
        users.mutableUsers = false;
        users.users.admin = {
          isNormalUser = true;
          extraGroups = [ "wheel" ];
          hashedPasswordFile = "/etc/credentials/admin";
          openssh.authorizedKeys.keys = [
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGVwaGVtZXJhbC12bS10ZXN0LWtleS1ub3QtcmVhbCE= vm-test"
          ];
        };
        environment.systemPackages = [
          pkgs.pamtester
          pkgs.cryptsetup
          python
        ];
      })
    ];
  };
  c = target.config;
  plan = {
    spec = {
      schema_version = 1;
      host = "fresh-test";
      checkout = "/reviewed-release";
      hardware_uuid = uuid;
      installation = "fresh";
      source_retention = "new-disks";
      disks = [
        {
          path = device;
          serial = "fresh-target";
          size_bytes = 8589934592;
        }
      ]
      ++ lib.optionals multidisk [
        {
          path = "/dev/disk/by-id/virtio-fresh-data";
          serial = "fresh-data";
          size_bytes = 2147483648;
        }
      ];
    };
    source = {
      revision = "disposable-vm-fixture";
      lock_sha256 = "vm-fixture";
    };
    config = {
      disks = {
        system = device;
      }
      // lib.optionalAttrs multidisk {
        data = "/dev/disk/by-id/virtio-fresh-data";
      };
      closure = toString c.system.build.toplevel;
      mounts = builtins.mapAttrs (_: m: { inherit (m) device fsType options; }) c.fileSystems;
      crypttab = c.environment.etc.crypttab.text or "";
      secure_boot = false;
      remote_unlock.enable = false;
      in_place = {
        root_fs_type = "btrfs";
        arrays = [ ];
        other_encrypted = lib.optional multidisk "luxnix-app-storage";
        secondary = lib.optionals multidisk [
          {
            name = "luxnix-app-storage";
            device = "/dev/disk/by-partlabel/disk-data-payload";
            fs_type = "btrfs";
          }
        ];
      };
      admin = {
        name = "admin";
        normal = true;
        wheel = true;
        hash_file = "/etc/credentials/admin";
        source = null;
        keys = c.users.users.admin.openssh.authorizedKeys.keys;
      };
      secret_contract = {
        vault_server = false;
        openbao = false;
        items = [
          { path = "/etc/credentials/admin"; }
          { path = "/etc/provisioning"; }
        ];
      };
    };
  };
  bundle = import ../../lx_administration/storage/fresh-installer.nix {
    inherit pkgs plan;
    source = repoRoot;
    inherit (c.system.build) diskoScript;
    closure = c.system.build.toplevel;
    disks = c.disko.devices.disk;
  };
  interact = pkgs.writeText "fresh-install-interact.py" ''
    import json, os, signal, time
    from pathlib import Path
    import pexpect
    command = "${bundle}/bin/luxnix-install --state /custody/state --credentials /custody/credentials --apply"
    journal = Path("/custody/state/fresh-install.json")
    def record():
        return json.loads(journal.read_text()) if journal.exists() else {}
    def wait_stage(child, stage):
        until = time.monotonic() + 600
        while time.monotonic() < until:
            if record().get("status") == stage:
                return
            try:
                child.read_nonblocking(65536, timeout=.01)
            except pexpect.TIMEOUT:
                pass
        raise AssertionError("did not reach " + stage)
    child = pexpect.spawn(command, encoding="utf-8", timeout=600)
    child.expect("Admin password for this host")
    child.sendline("vm-password")
    child.expect("to authorize this installation:")
    child.sendline("ERASE fresh-test fresh-target${lib.optionalString multidisk " fresh-data"}")
    for _ in range(${if multidisk then "2" else "1"}):
        child.expect("Enter password for .*:")
        child.sendline("vm-disk-password")
        child.expect("again to be safe:")
        child.sendline("vm-disk-password")
    wait_stage(child, "storage-ready")
    original_mounts = record()["mounts"]
    child.kill(signal.SIGKILL)
    child.close()
    # The actual resume CLI preserves any credentials already published.
    # Keep the installer child alive when its controlling process is killed.
    child = pexpect.spawn(command + " --resume", encoding="utf-8", timeout=600, ignore_sighup=True)
    child.expect("Admin password for this host")
    child.sendline("vm-password")
    child.expect("to authorize this installation:")
    child.sendline("RESUME fresh-test fresh-target${lib.optionalString multidisk " fresh-data"}")
    ${lib.optionalString multidisk ''
      child.expect("Existing disk passphrase for luxnix-app-storage:")
      child.sendline("vm-disk-password")
    ''}
    wait_stage(child, "installing")
    until = time.monotonic() + 10
    installer = None
    while time.monotonic() < until:
        children = Path(f"/proc/{child.pid}/task/{child.pid}/children").read_text().split()
        if children:
            installer = int(children[0])
            break
        time.sleep(.005)
    assert installer, "nixos-install child was not observed"
    os.kill(installer, signal.SIGSTOP)
    child.kill(signal.SIGKILL)
    child.close()
    # Orphaning a stopped process group can continue it; stop it again now
    # that the controller is gone, while ignoring the terminal hangup.
    os.kill(installer, signal.SIGSTOP)
    import subprocess
    refused = subprocess.run(command.split() + ["--resume"], capture_output=True, text=True)
    assert refused.returncode != 0
    assert "Another installer operation is active" in refused.stderr, refused.stderr
    os.kill(installer, signal.SIGCONT)
    subprocess.run(["timeout", "180", "flock", "/run/lock/luxnix-boot-install.lock", "true"], check=True)
    before = Path("/mnt/etc/credentials/admin").stat()
    child = pexpect.spawn(command + " --resume", encoding="utf-8", timeout=600)
    child.expect("Admin password for this host")
    child.sendline("vm-password")
    child.expect("to authorize this installation:")
    child.sendline("RESUME fresh-test fresh-target${lib.optionalString multidisk " fresh-data"}")
    child.expect("cold-boot acceptance is still pending")
    child.expect(pexpect.EOF)
    child.close()
    assert child.exitstatus == 0
    after = Path("/mnt/etc/credentials/admin").stat()
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)
    assert record()["mounts"] == original_mounts
  '';
in
pkgs.testers.runNixOSTest {
  name = "fresh-encrypted-install${lib.optionalString multidisk "-multidisk"}";
  nodes.machine = {
    documentation.enable = false;
    virtualisation = {
      diskImage = null;
      memorySize = 3072;
      qemu.options = [ "-uuid ${uuid}" ];
      emptyDiskImages = [
        {
          size = 8192;
          driveConfig.deviceExtraOpts.serial = "fresh-target";
        }
        {
          size = 128;
          driveConfig.deviceExtraOpts.serial = "fresh-custody";
        }
      ]
      ++ lib.optionals multidisk [
        {
          size = 2048;
          driveConfig.deviceExtraOpts.serial = "fresh-data";
        }
      ];
    };
    environment.systemPackages = [
      bundle
      python
      pkgs.cryptsetup
      pkgs.e2fsprogs
    ];
  };
  testScript = ''
    import shlex
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("printf custody | cryptsetup luksFormat --batch-mode --key-file - /dev/disk/by-id/virtio-fresh-custody")
    machine.succeed("printf custody | cryptsetup open --key-file - /dev/disk/by-id/virtio-fresh-custody custody")
    machine.succeed("mkfs.ext4 /dev/mapper/custody; mkdir -p /custody; mount /dev/mapper/custody /custody; chmod 700 /custody")
    machine.succeed("mkdir -p /custody/credentials/etc/credentials; chmod -R 700 /custody/credentials")
    machine.succeed("install -m 600 ${hash} /custody/credentials/etc/credentials/admin")
    machine.succeed("mkdir -m 700 /custody/credentials/etc/provisioning")
    machine.succeed("python -c \"from pathlib import Path; p=Path('/custody/credentials/etc/provisioning'); [(p/str(i)).write_bytes(b'fixture-key') for i in range(64)]; [f.chmod(0o600) for f in p.iterdir()]\"")
    machine.succeed("${python}/bin/python ${interact}", timeout=900)
    machine.succeed("cryptsetup status cryptroot | grep LUKS2")
    machine.succeed("test -s /mnt/etc/credentials/admin")
    machine.fail("${bundle}/bin/luxnix-install --state /custody/state --credentials /custody/credentials --apply")
    machine.succeed("sync")
    machine.shutdown()
    original = machine
    command = shlex.split("${pkgs.qemu}/bin/qemu-system-x86_64 -enable-kvm -m 2048") + [
      "-drive", f"file={original.state_dir}/empty0.qcow2,if=none,id=root",
      "-device", "virtio-blk-pci,drive=root,serial=fresh-target",
      "-drive", "if=pflash,format=raw,unit=0,readonly=on,file=${pkgs.OVMF.firmware}",
      "-drive", "if=pflash,format=raw,unit=1,readonly=on,file=${pkgs.OVMF.variables}",
    ]
    ${lib.optionalString multidisk ''
      command += ["-drive", f"file={original.state_dir}/empty2.qcow2,if=none,id=data",
                  "-device", "virtio-blk-pci,drive=data,serial=fresh-data"]
    ''}
    booted = create_machine(start_command=shlex.join(command), name="installed")
    driver.machines_qemu.append(booted)
    booted.start()
    booted.wait_for_console_text("[Pp]assphrase")
    booted.send_chars("vm-disk-password\n")
    booted.wait_for_unit("multi-user.target")
    booted.succeed("cryptsetup status cryptroot | grep LUKS2")
    ${lib.optionalString multidisk ''
      booted.succeed("cryptsetup status luxnix-app-storage | grep LUKS2")
      booted.succeed("findmnt -no SOURCE /var/lib/lx-annotate | grep luxnix-app-storage")
    ''}
    booted.succeed("printf 'vm-password\\n' | pamtester login admin authenticate")
  '';
}
