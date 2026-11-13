# migration-boot kexec on a running host: no reboot and no firmware. The target
# switches into the RAM environment; the controller reaches it only with the SSH
# host key pinned before the switch, and its screen offers a root terminal after a
# typed phrase. Disposable VMs and synthetic keys only.
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
      --bundle ${bundle} --output /home/operator/migration-target-kexec "$@"
  '';
  checkBackupKey = pkgs.writeShellScript "check-backup-key" ''
    export PYTHONPATH=${repoRoot}
    export PATH=${pkgs.lib.makeBinPath [ pkgs.coreutils ]}:$PATH
    exec ${python}/bin/python - <<'PY'
    from pathlib import Path
    from lx_administration.storage.host_backup import ensure_key
    custody = Path('/run/kexec-test/custody')
    key = ensure_key(custody, 'target')
    assert key.parent == custody and len(key.read_bytes()) == 64
    original = key.read_bytes()
    assert ensure_key(custody, 'target').read_bytes() == original
    assert (custody / 'target').stat().st_uid == 0
    assert list((custody / 'target').iterdir()) == []
    PY
  '';
in
pkgs.testers.runNixOSTest {
  name = "migration-kexec";
  enableOCR = true;
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
      users.users.operator = {
        isNormalUser = true;
        extraGroups = [ "wheel" ];
      };
      # Only the disposable test administrator has passwordless sudo.
      security.sudo.wheelNeedsPassword = false;
    };
  };
  testScript = ''
    start_all()
    target.wait_for_unit("multi-user.target")
    controller.wait_for_unit("multi-user.target")

    # Private tmpfs workspace, as an operator's runtime directory provides.
    target.succeed("mkdir -p /run/kexec-test && mount -t tmpfs -o size=3G,mode=0700 tmpfs /run/kexec-test")
    target.succeed("chown operator:users /run/kexec-test")
    controller.succeed("install -D -m 0600 ${keys.snakeOilPrivateKey} /root/.ssh/id_ed25519")

    with subtest("Normal user handles root-only UUID and root-owned custody host folder"):
        target.fail("runuser -u operator -- cat /sys/class/dmi/id/product_uuid")
        target.succeed("install -d -o operator -g users -m 0700 /run/kexec-test/custody")
        target.succeed("mkdir /run/kexec-test/custody/target && chmod 0755 /run/kexec-test/custody/target")
        target.succeed("runuser -u operator -- ${checkBackupKey}")

    with subtest("Preview pins a host key and loads nothing"):
        preview = target.succeed("runuser -u operator -- /etc/migration-kexec")
        print(preview)
        assert "Preview only; nothing was loaded" in preview
        assert "Host key: 256 SHA256:" in preview
        target.succeed("grep -x 0 /sys/kernel/kexec_loaded")
        known_hosts = target.succeed("cat /home/operator/migration-target-kexec/known_hosts")
        assert known_hosts.startswith("[192.168.1.2]:2222 ssh-ed25519 "), known_hosts

    with subtest("A wrong confirmation loads nothing"):
        target.fail("echo nope | runuser -u operator -- script -qec '/etc/migration-kexec --apply' /dev/null")
        target.succeed("grep -x 0 /sys/kernel/kexec_loaded")

    # Each run pins a new key: read it while this host waits for the phrase, as
    # an operator copies known_hosts before typing it.
    target.succeed(
        "((sleep 45; echo 'START RAM target') | runuser -u operator -- script -qec '/etc/migration-kexec --apply' /dev/null"
        " > /tmp/kexec.log 2>&1 &)"
    )
    target.wait_until_succeeds("grep -q 'Type START RAM target' /tmp/kexec.log", timeout=40)
    known_hosts = target.succeed("cat /home/operator/migration-target-kexec/known_hosts")
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

    with subtest("The screen shows how to connect"):
        controller.succeed(ssh + "systemctl is-active luxnix-migration-access.service")
        controller.fail(ssh + "systemctl is-active getty@tty1.service")
        # The screen is the last console, so boot status and messages reach it.
        cmdline = controller.succeed(ssh + "cat /proc/cmdline")
        assert cmdline.index("console=ttyS0") < cmdline.index("console=tty0"), cmdline
        # Verify actual pixels: an active unit and a working serial console do
        # not establish that the physical-style display is visible after kexec.
        target.wait_for_text("(?i)migration environment", timeout=90)
        target.screenshot("migration-kexec-visible-console")

    with subtest("The screen opens a root terminal only after the typed phrase"):
        # Keys go through the emulated US keyboard while the RAM environment uses
        # the fleet's German layout: there "&" is typed for "/".
        def typed(command):
            assert not set("yz-") & set(command), command
            target.send_chars(command.replace("/", "&") + "\n")

        typed("touch /run/before")
        target.wait_for_text("(?i)not opened", timeout=90)
        controller.fail(ssh + "test -e /run/before")
        typed("LOCAL TERMINAL")
        target.wait_for_text("(?i)root terminal in ram", timeout=90)
        typed("touch /run/opened")
        controller.wait_until_succeeds(ssh + "test -e /run/opened", timeout=60)
        target.screenshot("migration-kexec-local-terminal")
        # Leaving the terminal brings the access screen back, closed again.
        typed("exit")
        controller.wait_until_succeeds(ssh + "'systemctl show -P NRestarts luxnix-migration-access.service | grep -x 1'", timeout=60)
        target.wait_for_text("(?i)for a root terminal", timeout=90)
        typed("touch /run/after")
        target.wait_for_text("(?i)not opened", timeout=90)
        controller.fail(ssh + "test -e /run/after")

    with subtest("Any other host key is refused"):
        controller.succeed("ssh-keygen -q -t ed25519 -N ''' -f /root/other")
        controller.succeed("printf '[192.168.1.2]:2222 %s\\n' \"$(cut -d' ' -f1,2 /root/other.pub)\" > /root/other_known_hosts")
        controller.fail(ssh.replace("/root/pinned_known_hosts", "/root/other_known_hosts") + "true")
        # Only the recovery port is open; no other SSH listens.
        controller.fail("ssh -o ConnectTimeout=5 -o BatchMode=yes -p 22 root@192.168.1.2 true")

    target.crash()
  '';
}
