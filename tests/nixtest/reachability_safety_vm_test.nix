_: {
  suites."reachability safety" = {
    pos = __curPos;
    tests = [
      {
        name = "boot-remains-reachable-when-secret-bootstrap-fails";
        type = "vm";
        vmConfig = {
          nodes.machine = {
            services.openssh = {
              enable = true;
              settings.PasswordAuthentication = false;
            };
            networking.firewall.allowedTCPPorts = [ 22 ];

            systemd.services = {
              vault-auth-setup = {
                description = "Intentionally failing vault bootstrap";
                wantedBy = [ "multi-user.target" ];
                serviceConfig = {
                  Type = "oneshot";
                  ExecStart = "/bin/sh -c 'exit 1'";
                };
              };

              managed-secrets-setup = {
                description = "Service blocked by failed vault bootstrap";
                wantedBy = [ "multi-user.target" ];
                after = [ "vault-auth-setup.service" ];
                requires = [ "vault-auth-setup.service" ];
                serviceConfig = {
                  Type = "oneshot";
                  ExecStart = "/bin/sh -c 'echo should-not-run > /run/managed-secrets-ran'";
                };
              };

              fake-app = {
                description = "App that should never make the host unreachable";
                wantedBy = [ "multi-user.target" ];
                after = [ "managed-secrets-setup.service" ];
                requires = [ "managed-secrets-setup.service" ];
                serviceConfig = {
                  Type = "oneshot";
                  ExecStart = "/bin/sh -c 'exit 1'";
                };
              };
            };
          };
          testScript =
            # py
            ''
              machine.wait_for_unit("sshd.service")
              machine.wait_for_open_port(22)
              machine.wait_until_succeeds("systemctl is-failed vault-auth-setup.service")
              machine.succeed("systemctl is-active sshd.service")
              machine.succeed("echo host-still-responsive")
            '';
        };
      }
      {
        name = "failing-application-service-does-not-take-down-admin-access";
        type = "vm";
        vmConfig = {
          nodes.machine = {
            services.openssh = {
              enable = true;
              settings.PasswordAuthentication = false;
            };
            networking.firewall.allowedTCPPorts = [ 22 ];

            systemd.services.fake-critical-app = {
              description = "Critical app failure simulation";
              wantedBy = [ "multi-user.target" ];
              serviceConfig = {
                Type = "simple";
                Restart = "no";
                ExecStart = "/bin/sh -c 'echo failing-app >&2; exit 1'";
              };
            };
          };
          testScript =
            # py
            ''
              machine.wait_for_unit("sshd.service")
              machine.wait_for_open_port(22)
              machine.wait_until_succeeds("systemctl is-failed fake-critical-app.service")
              machine.succeed("systemctl is-active sshd.service")
              machine.succeed("uname -a")
            '';
        };
      }
    ];
  };
}
