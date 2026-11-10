# migration-boot kexec on a running host: no reboot, no firmware, no console. The
# target switches into the RAM environment; the controller reaches it only with the
# SSH host key pinned before the switch. Disposable VMs and synthetic keys only.
{
  pkgs,
  repoRoot,
  migrationEnvironment,
}:
let
  keys = import "${pkgs.path}/nixos/tests/ssh-keys.nix" pkgs;
  hardwareUuid = "11111111-1111-4111-8111-111111111111";
  spec = {
    host = "target";
    boot_trust = "host-kexec";
    console = "tty1";
    hardware_uuid = hardwareUuid;
    revision = "a" + builtins.substring 1 39 (builtins.hashString "sha1" "kexec-test");
    interface = "eth1";
    address = "192.168.1.2/24";
    gateway = null;
    controller_cidr = "192.168.1.1/32";
    authorized_keys = [ keys.snakeOilPublicKey ];
    recovery = {
      uuid = "22222222-2222-4222-8222-222222222222";
      fstype = "ext4";
      luks_uuid = null;
    };
    target_serials = [ "root-disk" ];
    # Mirrors conf/migration-environment.yml.
    policy = {
      schema_version = 2;
      ssh_port = 2222;
      minimum_memory_mib = 4096;
      maximum_image_mib = 384;
      esp_reserve_mib = 64;
      maximum_payload_mib = 1024;
    };
  };
  bundle = (migrationEnvironment spec).config.system.build.kexecBundle;
  python = pkgs.python3.withPackages (p: [
    p.pydantic
    p.pyyaml
  ]);
  start = pkgs.writeShellScript "migration-kexec" ''
    export PATH=${
      pkgs.lib.makeBinPath [
        python
        pkgs.kexec-tools
        pkgs.openssh
        pkgs.util-linux
        pkgs.systemd
        pkgs.coreutils
      ]
    }:$PATH
    export PYTHONPATH=${repoRoot} XDG_RUNTIME_DIR=/run/kexec-test
    exec python -m lx_administration.storage.migration_boot kexec \
      --bundle ${bundle} --output /root/migration-target-kexec "$@"
  '';
in
pkgs.testers.runNixOSTest {
  name = "migration-kexec";
  nodes = {
    controller = {
      environment.systemPackages = [ pkgs.openssh ];
    };
    target = {
      virtualisation = {
        memorySize = 6144;
        qemu.options = [ "-uuid ${hardwareUuid}" ];
      };
      environment.systemPackages = [ pkgs.util-linux ];
      environment.etc."migration-kexec".source = start;
    };
  };
  testScript = ''
    start_all()
    target.wait_for_unit("multi-user.target")
    controller.wait_for_unit("multi-user.target")

    # Private tmpfs workspace, as an operator's runtime directory provides.
    target.succeed("mkdir -p /run/kexec-test && mount -t tmpfs -o size=3G,mode=0700 tmpfs /run/kexec-test")
    controller.succeed("install -D -m 0600 ${keys.snakeOilPrivateKey} /root/.ssh/id_ed25519")

    with subtest("Preview pins a host key and loads nothing"):
        preview = target.succeed("/etc/migration-kexec")
        print(preview)
        assert "Preview only; nothing was loaded" in preview
        assert "Host key: 256 SHA256:" in preview
        target.succeed("grep -x 0 /sys/kernel/kexec_loaded")
        known_hosts = target.succeed("cat /root/migration-target-kexec/known_hosts")
        assert known_hosts.startswith("[192.168.1.2]:2222 ssh-ed25519 "), known_hosts

    with subtest("A wrong confirmation loads nothing"):
        target.fail("echo nope | script -qec /etc/migration-kexec\\ --apply /dev/null")
        target.succeed("grep -x 0 /sys/kernel/kexec_loaded")

    # Each run pins a new key: read it while this host waits for the phrase, as
    # an operator copies known_hosts before typing it.
    target.succeed(
        "((sleep 45; echo 'START RAM target') | script -qec '/etc/migration-kexec --apply' /dev/null"
        " > /tmp/kexec.log 2>&1 &)"
    )
    target.wait_until_succeeds("grep -q 'Type START RAM target' /tmp/kexec.log", timeout=40)
    known_hosts = target.succeed("cat /root/migration-target-kexec/known_hosts")
    # The running system is gone after this; the RAM environment has no test agent.
    target.connected = False
    controller.succeed(f"printf '%s' '{known_hosts}' > /root/pinned_known_hosts")

    ssh = (
        "ssh -o UserKnownHostsFile=/root/pinned_known_hosts -o StrictHostKeyChecking=yes"
        " -o ConnectTimeout=5 -o BatchMode=yes -p 2222 root@192.168.1.2 "
    )

    with subtest("The controller reaches the RAM environment with the pinned key"):
        controller.wait_until_succeeds(ssh + "true", timeout=600)
        assert controller.succeed(ssh + "hostname").strip() == "target-migration"
        assert controller.succeed(ssh + "findmnt -no FSTYPE /").strip() == "tmpfs"
        controller.succeed(ssh + "systemctl is-active luxnix-migration-admission.service")
        controller.succeed(ssh + "test -x /run/current-system/sw/bin/luxnix-migration")
        assert controller.succeed(ssh + "ip -brief link show eth1").startswith("eth1")

    with subtest("The screen shows how to connect instead of a login"):
        controller.succeed(ssh + "systemctl is-active luxnix-migration-access.service")
        controller.fail(ssh + "systemctl is-active getty@tty1.service")
        # The screen is the last console, so boot status and messages reach it.
        cmdline = controller.succeed(ssh + "cat /proc/cmdline")
        assert cmdline.index("console=ttyS0") < cmdline.index("console=tty0"), cmdline

    with subtest("Any other host key is refused"):
        controller.succeed("ssh-keygen -q -t ed25519 -N ''' -f /root/other")
        controller.succeed("printf '[192.168.1.2]:2222 %s\\n' \"$(cut -d' ' -f1,2 /root/other.pub)\" > /root/other_known_hosts")
        controller.fail(ssh.replace("/root/pinned_known_hosts", "/root/other_known_hosts") + "true")
        # Only the recovery port is open; no other SSH listens.
        controller.fail("ssh -o ConnectTimeout=5 -o BatchMode=yes -p 22 root@192.168.1.2 true")

    target.crash()
  '';
}
