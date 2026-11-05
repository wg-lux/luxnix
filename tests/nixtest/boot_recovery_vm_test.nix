# Synthetic credentials and fault injection are confined to this disposable VM.
{
  pkgs,
  hostConfig,
}:
let
  inherit (pkgs) lib;
  names = [
    "vault-auth-setup"
    "managed-secrets-setup"
    "lx-annotate"
  ];
  dependencies =
    values: builtins.filter (name: builtins.elem name (map (n: "${n}.service") names)) values;
  graph = name: {
    after = dependencies hostConfig.systemd.services.${name}.after;
    requires = dependencies hostConfig.systemd.services.${name}.requires;
  };
  hash = pkgs.runCommand "disposable-login-hash" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    printf 'vm-recovery-password\n' | openssl passwd -6 -stdin > "$out"
  '';
  validators = lib.genAttrs [ "admin" "client" ] (
    user:
    hostConfig.system.preSwitchChecks.${
      if user == "admin" then "adminCredential" else "clientCredential"
    }
  );
  sources = builtins.attrValues hostConfig.luxnix.storage.operatorUnlocked.migration.accountHashes;
in
pkgs.testers.runNixOSTest {
  name = "gc02-boot-recovery";
  enableOCR = true;
  nodes.machine = {
    virtualisation.memorySize = 3072;
    virtualisation.cores = 2;
    services = {
      xserver.enable = true;
      desktopManager.plasma6.enable = true;
      displayManager = {
        autoLogin = hostConfig.services.displayManager.autoLogin;
        sddm = {
          enable = true;
          inherit (hostConfig.services.displayManager.sddm) theme settings;
          wayland.enable = hostConfig.services.displayManager.sddm.wayland.enable;
        };
      };
    };
    users.mutableUsers = false;
    users.users = lib.genAttrs [ "admin" "client-user" ] (name: {
      isNormalUser = true;
      uid = if name == "admin" then 1000 else 1003;
      hashedPasswordFile = "/var/lib/luxnix-account/${
        if name == "admin" then "admin" else "client"
      }-password.hash";
    });
    system = {
      switch.enable = true;
      activationScripts = {
        testAccounts = {
          deps = [ "specialfs" ];
          text =
            lib.concatMapStrings (source: ''
              if [ ! -e ${lib.escapeShellArg source} ]; then
                install -D -m 0600 ${hash} ${lib.escapeShellArg source}
              fi
            '') sources
            + hostConfig.system.activationScripts.luxnixPrepareBootAccountHashes.text;
        };
        testValidate = {
          deps = [ "testAccounts" ];
          text = validators.admin + validators.client;
        };
        users.deps = [ "testValidate" ];
      };
      preSwitchChecks = validators;
    };
    environment.systemPackages = [
      pkgs.pamtester
      pkgs.openssl
    ];
    systemd.services = {
      vault-auth-setup = (graph "vault-auth-setup") // {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = builtins.intersectAttrs {
          Type = null;
          RemainAfterExit = null;
          Restart = null;
          RestartSec = null;
          TimeoutStartSec = null;
          ExecStartPost = null;
        } hostConfig.systemd.services.vault-auth-setup.serviceConfig;
        script = ''
          if [ -e /run/auth-hang ]; then sleep 120; fi
          test -e /run/auth-available
        '';
      };
      managed-secrets-setup = (graph "managed-secrets-setup") // {
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = "test ! -e /run/secrets-unavailable";
      };
      lx-annotate = (graph "lx-annotate") // {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = "echo started >> /run/application-starts";
      };
    };
  };
  testScript = ''
    start_all()
    machine.wait_for_unit("multi-user.target")
    machine.fail("systemctl is-active lx-annotate.service")
    machine.fail("test -e /run/application-starts")
    machine.succeed("touch /run/auth-available")
    machine.wait_until_succeeds("systemctl is-active lx-annotate.service", timeout=100)
    machine.succeed("test $(wc -l < /run/application-starts) = 1")
    machine.succeed("systemctl start vault-auth-setup.service lx-annotate.service")
    machine.succeed("test $(wc -l < /run/application-starts) = 1")

    # Real timeout and retry, without manual dependency restarts after recovery.
    machine.succeed("touch /run/auth-hang; systemctl restart --no-block vault-auth-setup.service")
    machine.wait_until_succeeds("test $(systemctl show vault-auth-setup -p Result --value) = timeout", timeout=65)
    machine.succeed("rm /run/auth-hang")
    machine.wait_until_succeeds("systemctl is-active lx-annotate.service", timeout=100)
    machine.succeed("test $(wc -l < /run/application-starts) = 2")

    # Authenticate both immutable users using real PAM, before and after activation.
    def authenticate():
        for user in ["admin", "client-user"]:
            machine.succeed(f"printf 'vm-recovery-password\\n' | pamtester sddm {user} authenticate acct_mgmt")
            machine.fail(f"printf 'wrong-password\\n' | pamtester sddm {user} authenticate")
    authenticate()
    shadow = machine.succeed("sha256sum /etc/shadow")
    machine.succeed("printf 'stale-source-password\\n' | openssl passwd -6 -stdin > /run/stale.hash; chmod 600 /run/stale.hash")
    machine.succeed("for source in ${lib.escapeShellArgs sources}; do cp -p /run/stale.hash $source; done")
    machine.succeed("/run/current-system/bin/switch-to-configuration test")
    assert machine.succeed("sha256sum /etc/shadow") == shadow
    authenticate()
    machine.succeed("cp -p /var/lib/luxnix-account/client-password.hash /run/client.saved; printf '!\\n' > /var/lib/luxnix-account/client-password.hash")
    machine.fail("/run/current-system/bin/switch-to-configuration test")
    assert machine.succeed("sha256sum /etc/shadow") == shadow
    machine.succeed("cp -p /run/client.saved /var/lib/luxnix-account/client-password.hash")
    # Even a valid replacement in the authoritative boot file is not consent.
    for user, stem in [("admin", "admin"), ("client-user", "client")]:
        target = f"/var/lib/luxnix-account/{stem}-password.hash"
        machine.succeed(f"cp -p {target} /run/account.saved; cp -p /run/stale.hash {target}")
        machine.fail("/run/current-system/bin/switch-to-configuration test")
        machine.fail("/run/current-system/bin/switch-to-configuration boot")
        machine.fail("/run/current-system/activate")
        assert machine.succeed("sha256sum /etc/shadow") == shadow
        machine.succeed(f"cp -p /run/account.saved {target}")
        # Simulate an explicit password-entry operation on the live account:
        # a later rebuild must not undo it from the older persistent file.
        machine.succeed(f"printf '{user}:' > /run/change; cat /run/stale.hash >> /run/change; chpasswd -e < /run/change")
        changed = machine.succeed("sha256sum /etc/shadow")
        machine.fail("/run/current-system/bin/switch-to-configuration test")
        assert machine.succeed("sha256sum /etc/shadow") == changed
        machine.succeed(f"cp -p /run/stale.hash {target}")
        machine.succeed("/run/current-system/bin/switch-to-configuration test")
        assert machine.succeed("sha256sum /etc/shadow") == changed
        machine.succeed(f"printf 'stale-source-password\\n' | pamtester sddm {user} authenticate acct_mgmt")
        # Restore the synthetic fixture through the same explicit path.
        machine.succeed(f"printf '{user}:' > /run/change; cat /run/account.saved >> /run/change; chpasswd -e < /run/change; cp -p /run/account.saved {target}")
        # chpasswd also updates password-age metadata; snapshot after consent.
        shadow = machine.succeed("sha256sum /etc/shadow")
    authenticate()
    # A valid hash behind a symlink passes the format check, but preparation
    # rejects the path. That failure must abort before immutable users update.
    machine.succeed("rm /var/lib/luxnix-account/client-password.hash; ln -s /run/client.saved /var/lib/luxnix-account/client-password.hash")
    machine.fail("/run/current-system/bin/switch-to-configuration test")
    assert machine.succeed("sha256sum /etc/shadow") == shadow
    machine.succeed("rm /var/lib/luxnix-account/client-password.hash; cp -p /run/client.saved /var/lib/luxnix-account/client-password.hash")
    machine.shutdown()
    machine.start()
    machine.wait_for_unit("multi-user.target")
    assert machine.succeed("sha256sum /etc/shadow") == shadow
    authenticate()
    machine.fail("systemctl is-active lx-annotate.service")
    machine.wait_for_unit("display-manager.service")
    machine.wait_for_file("/run/sddm")
    # Breeze hides controls after 60 seconds idle. Exercise its normal wakeup.
    machine.send_key("ctrl")
    machine.wait_for_text("(?i)admin", timeout=30)
    machine.wait_for_text("(?i)client.user", timeout=30)
    # OCR can take longer than the idle timeout on a busy builder.
    machine.send_key("ctrl")
    machine.sleep(1)
    machine.screenshot("desktop-chooser")
  '';
}
