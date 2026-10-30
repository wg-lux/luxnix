{ repoRoot, ... }:
let
  fixture = import ./openbao_local_vm_test.nix {
    inherit repoRoot;
    sealMode = "passphrase";
  };
in
{
  name = "storage-login-access";
  nodes.server = { lib, pkgs, ... }: {
    imports = [
      fixture.nodes.server
      (repoRoot + "/modules/nixos/luxnix/storage-access")
    ];
    virtualisation.memorySize = lib.mkForce 3072;
    # qemu-vm replaces fileSystems wholesale. Declare the two disposable mounts
    # through its filesystem interface; production hosts use the storage module.
    virtualisation.fileSystems = {
      "/var/lib/test-volume" = {
        device = "/dev/mapper/test";
        fsType = "ext4";
        options = [
          "nofail"
          "noauto"
          "x-systemd.requires=luxnix-storage-unlock-test.service"
        ];
      };
      "/srv/private" = {
        device = "/var/lib/test-volume/private";
        fsType = "none";
        options = [
          "nofail"
          "bind"
          "noauto"
          "x-systemd.requires=luxnix-storage-permissions-test.service"
        ];
        depends = [ "/var/lib/test-volume" ];
      };
    };
    luxnix.storage.loginAccess = {
      enable = true;
      users = [
        "admin"
        "client-user"
      ];
      pamServices = [ "login" ];
    };
    luxnix.storage.operatorUnlocked = {
      layout = "legacy-containers";
      volumes = lib.mkForce {
        test = {
          container = "/var/lib/test.luks";
          mountPoint = "/var/lib/test-volume";
          luksUUID = "11111111-1111-1111-1111-111111111111";
        };
      };
      bindMounts."/srv/private" = {
        volume = "test";
        directory = "private";
      };
      guardedServices.probe = [ "/srv/private" ];
      startupServices = [ "probe" ];
    };
    users.users.admin = {
      isNormalUser = true;
      password = "test-admin-password";
    };
    users.users.client-user = {
      isNormalUser = true;
      password = "test-client-password";
    };
    systemd.services = {
      fixture-boot-unlock.wantedBy = lib.mkForce [ ];
      probe = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig.ExecStart = "${pkgs.coreutils}/bin/sleep infinity";
      };
    };
    environment.systemPackages = [ pkgs.pamtester ];
  };
  testScript = ''
    start_all()
    server.wait_for_unit("systemd-user-sessions.service")
    server.fail("test -e /dev/mapper/test")
    server.succeed("test $(stat -c '%a' /var/lib/test-volume) = 700")
    server.succeed("python /etc/local-guest.py prepare")
    # Enrollment is normally completed before selecting the login profile.
    server.succeed("touch /run/luxnix-storage-access/unlocked")
    server.succeed("python /etc/local-guest.py enroll")
    server.succeed("python /etc/local-guest.py adopt")
    server.succeed("systemctl start luxnix-storage-unlock-test.service")
    server.succeed("mount /dev/mapper/test /mnt; mkdir /mnt/private; umount /mnt")
    server.succeed("cat /etc/fstab; systemctl list-unit-files '*test*' '*private*' --no-pager")
    with subtest("both authenticated logins enroll and logout preserves background work"):
      for user, password in [("admin", "test-admin-password"), ("client-user", "test-client-password")]:
        server.succeed(f"printf '%s\\n' '{password}' | pamtester login {user} authenticate open_session close_session")
        server.succeed("systemctl is-active probe.service")
        server.succeed(f"test -f /var/lib/openbao-bootstrap/login/{user}.json")
    with subtest("backing root is inaccessible to ordinary accounts"):
      server.succeed("test $(stat -c '%U:%G:%a' /var/lib/test-volume) = root:root:700")
      server.fail("su -s /bin/sh admin -c 'ls /var/lib/test-volume'")
      server.fail("su -s /bin/sh client-user -c 'luxnix-storage-access lock'")
    with subtest("remote root lock stops consumers, unmounts and erases the staged seal"):
      server.succeed("luxnix-storage-access lock")
      server.fail("systemctl is-active probe.service")
      server.fail("test -e /dev/mapper/test")
      server.fail("test -e /run/luxnix-openbao-seal/seal.key")
      server.execute("systemctl --no-block start probe.service")
      server.fail("test -e /dev/mapper/test")
    with subtest("failed authentication cannot reopen storage"):
      server.fail("printf '%s\\n' wrong | pamtester login admin authenticate open_session")
      server.fail("test -e /dev/mapper/test")
    with subtest("client login reopens storage without the admin or recovery passphrase"):
      server.succeed("printf '%s\\n' test-client-password | pamtester login client-user authenticate open_session close_session")
      server.succeed("systemctl is-active probe.service")
    with subtest("remote unlock and busy-filesystem lock failure"):
      server.succeed("luxnix-storage-access lock")
      # Detach the fixture's controlling console so getpass reads the synthetic
      # pipe. Operators use an SSH TTY; no production password enters a pipe.
      server.succeed("printf '%s' test-admin-password | setsid --wait luxnix-storage-access unlock --user admin")
      server.succeed("systemctl is-active probe.service")
      server.succeed("nohup sh -c 'cd /srv/private; exec sleep 300' >/dev/null 2>&1 & echo $! > /run/busy.pid")
      server.sleep(1)
      server.fail("luxnix-storage-access lock")
      server.succeed("test -e /dev/mapper/test; test -e /run/luxnix-openbao-seal/seal.key")
      server.succeed("kill $(cat /run/busy.pid)")
      server.succeed("luxnix-storage-access lock")
      server.fail("test -e /dev/mapper/test")
      server.succeed("test $(stat -c '%a' /var/lib/test-volume) = 700")
    with subtest("cold boot leaves storage closed until a successful login"):
      server.shutdown()
      server.start()
      server.wait_for_unit("systemd-user-sessions.service")
      server.fail("test -e /dev/mapper/test")
      server.succeed("printf '%s\\n' test-admin-password | pamtester login admin authenticate open_session close_session")
      server.succeed("systemctl is-active probe.service")
  '';
}
