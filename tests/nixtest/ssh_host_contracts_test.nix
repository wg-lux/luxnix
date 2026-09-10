{
  pkgs,
  ntlib,
  repoRoot,
  ...
}:
let
  flakeRef = toString repoRoot;
  linuxHosts = [
    "c-01"
    "gc-02"
    "gc-04"
    "gc-05"
    "gc-06"
    "gc-07"
    "gc-08"
    "gc-09"
    "gc-10"
    "gs-01"
    "gs-02"
    "s-01"
    "s-02"
    "s-03"
    "s-04"
  ];
  developerAccessHosts = [
    "gc-04"
    "gc-05"
    "gc-09"
    "gc-10"
    "gs-01"
    "gs-02"
    "s-04"
  ];
  baselineHosts = [
    "c-01"
    "gc-02"
    "gc-06"
    "gc-07"
    "gc-08"
    "s-01"
    "s-02"
    "s-03"
  ];
  registryHosts = [
    "gc-02"
    "gc-05"
    "gc-08"
    "gc-10"
  ];
in
{
  suites."ssh host contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "all-configured-linux-hosts-keep-secure-ssh-baseline";
        type = "script";
        script = ''
          ${ntlib.helpers.path [
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.jq
            pkgs.nix
          ]}
          ${ntlib.helpers.scriptHelpers}

          snapshot=$(nix eval --json --impure --expr '
            let
              flake = builtins.getFlake "${flakeRef}";
              hosts = ${builtins.toJSON linuxHosts};
            in
              builtins.map
                (host: let
                  c = flake.nixosConfigurations.${"$"}{host}.config;
                  registryFile = toString c.services.ssh.hostIdentity.registryFile;
                  settings = c.services.openssh.settings;
                  vpnInterface = c.services.ssh.network.vpnInterface;
                  vpnTcpPorts = c.networking.firewall.interfaces.${"$"}{vpnInterface}.allowedTCPPorts or [];
                in {
                  inherit host;
                  enable = c.services.openssh.enable;
                  openFirewall = c.services.openssh.openFirewall;
                  passwordAuth = c.services.openssh.settings.PasswordAuthentication;
                  ports = c.services.openssh.ports;
                  keyCount = builtins.length c.users.users.admin.openssh.authorizedKeys.keys;
                  hostIdentity = c.services.ssh.hostIdentity.enable;
                  rotationAllowed = c.services.ssh.hostIdentity.allowRotation;
                  kbdInteractive = settings.KbdInteractiveAuthentication;
                  permitRootLogin = settings.PermitRootLogin;
                  x11Forwarding = settings.X11Forwarding;
                  allowAgentForwarding = settings.AllowAgentForwarding;
                  allowTcpForwarding = settings.AllowTcpForwarding;
                  gatewayPorts = settings.GatewayPorts;
                  allowUsersOk = settings.AllowUsers == [c.user.admin.name];
                  globalFirewallSsh = builtins.elem 22 c.networking.firewall.allowedTCPPorts;
                  vpnFirewallSsh = builtins.elem 22 vpnTcpPorts;
                  registryInstalled =
                    builtins.any
                    (path: toString path == registryFile)
                    c.programs.ssh.knownHostsFiles;
                })
                hosts
          ')

          while IFS=$'\t' read -r \
            host \
            enable \
            open_firewall \
            password_auth \
            ports_ok \
            key_count \
            host_identity \
            rotation_allowed \
            kbd_interactive \
            permit_root_login \
            x11_forwarding \
            allow_agent_forwarding \
            allow_tcp_forwarding \
            gateway_ports \
            allow_users_ok \
            global_firewall_ssh \
            vpn_firewall_ssh \
            registry_installed
          do
            [ "$enable" = "true" ] || fail "expected SSH to be enabled for $host, got: $enable"
            [ "$open_firewall" = "false" ] || fail "expected services.openssh.openFirewall=false for $host"
            [ "$password_auth" = "false" ] || fail "expected PasswordAuthentication=false for $host, got: $password_auth"
            [ "$ports_ok" = "true" ] || fail "expected SSH ports [22] for $host"
            [ "$key_count" -ge 1 ] || fail "expected at least one admin authorized key for $host"
            [ "$host_identity" = "true" ] || fail "expected SSH host identity guard to be enabled for $host"
            [ "$rotation_allowed" = "false" ] || fail "expected SSH host key rotation override to be disabled for $host"
            [ "$kbd_interactive" = "false" ] || fail "expected KbdInteractiveAuthentication=false for $host"
            [ "$permit_root_login" = "no" ] || fail "expected PermitRootLogin=no for $host, got: $permit_root_login"
            [ "$x11_forwarding" = "false" ] || fail "expected X11Forwarding=false for $host"
            [ "$allow_agent_forwarding" = "false" ] || fail "expected AllowAgentForwarding=false for $host"
            [ "$allow_tcp_forwarding" = "no" ] || fail "expected AllowTcpForwarding=no for $host, got: $allow_tcp_forwarding"
            [ "$gateway_ports" = "no" ] || fail "expected GatewayPorts=no for $host, got: $gateway_ports"
            [ "$allow_users_ok" = "true" ] || fail "expected AllowUsers to contain only the configured admin user for $host"
            [ "$global_firewall_ssh" = "false" ] || fail "expected global firewall TCP/22 to be closed for $host"
            [ "$vpn_firewall_ssh" = "true" ] || fail "expected VPN interface firewall TCP/22 to be open for $host"
            [ "$registry_installed" = "true" ] || fail "expected host-key registry to be installed for $host"
          done < <(
            printf '%s' "$snapshot" | jq -r '.[] | [
              .host,
              (.enable|tostring),
              (.openFirewall|tostring),
              (.passwordAuth|tostring),
              ((.ports == [22])|tostring),
              (.keyCount|tostring),
              (.hostIdentity|tostring),
              (.rotationAllowed|tostring),
              (.kbdInteractive|tostring),
              .permitRootLogin,
              (.x11Forwarding|tostring),
              (.allowAgentForwarding|tostring),
              .allowTcpForwarding,
              .gatewayPorts,
              (.allowUsersOk|tostring),
              (.globalFirewallSsh|tostring),
              (.vpnFirewallSsh|tostring),
              (.registryInstalled|tostring)
            ] | @tsv'
          )
        '';
      }
      {
        name = "audited-hosts-have-canonical-ssh-host-key-registry-entries";
        type = "script";
        script = ''
          ${ntlib.helpers.path [
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.jq
            pkgs.nix
          ]}
          ${ntlib.helpers.scriptHelpers}

          snapshot=$(nix eval --json --impure --expr '
            let
              flake = builtins.getFlake "${flakeRef}";
              hosts = ${builtins.toJSON registryHosts};
            in
              builtins.map
                (host: let
                  c = flake.nixosConfigurations.${"$"}{host}.config;
                  hostNetwork = c.luxnix.generic-settings.network.hosts.${"$"}{host};
                in {
                  inherit host;
                  aliases = c.services.ssh.hostIdentity.aliases;
                  expected = c.services.ssh.hostIdentity.expectedEd25519PublicKey;
                  vpnIp = hostNetwork."ip-vpn";
                  registryFile = toString c.services.ssh.hostIdentity.registryFile;
                })
                hosts
          ')

          while IFS= read -r row; do
            host=$(printf '%s' "$row" | jq -r '.host')
            expected=$(printf '%s' "$row" | jq -r '.expected // empty')
            vpn_ip=$(printf '%s' "$row" | jq -r '.vpnIp')
            registry_file=$(printf '%s' "$row" | jq -r '.registryFile')

            [ -n "$expected" ] || fail "expected registry-derived ed25519 key for $host"
            printf '%s' "$row" | jq -e --arg host "$host" '.aliases | index($host)' >/dev/null || fail "expected alias $host for $host"
            printf '%s' "$row" | jq -e --arg host "$host.intern" '.aliases | index($host)' >/dev/null || fail "expected .intern alias for $host"
            printf '%s' "$row" | jq -e --arg vpn "$vpn_ip" '.aliases | index($vpn)' >/dev/null || fail "expected VPN IP alias for $host"

            registry_line=$(grep -E "(^|,)$host(,| )" "$registry_file" | grep 'ssh-ed25519' || true)
            [ -n "$registry_line" ] || fail "expected ed25519 registry line for $host"
            printf '%s' "$registry_line" | grep -F "$host.intern" >/dev/null || fail "expected registry .intern alias for $host"
            printf '%s' "$registry_line" | grep -F "$vpn_ip" >/dev/null || fail "expected registry VPN IP alias for $host"
          done < <(printf '%s' "$snapshot" | jq -c '.[]')
        '';
      }
      {
        name = "developer-access-hosts-keep-explicit-ssh-overlays";
        type = "script";
        script = ''
          ${ntlib.helpers.path [
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.jq
            pkgs.nix
          ]}
          ${ntlib.helpers.scriptHelpers}

          snapshot=$(nix eval --json --impure --expr '
            let
              flake = builtins.getFlake "${flakeRef}";
              hosts = ${builtins.toJSON developerAccessHosts};
            in
              builtins.map
                (host: {
                  inherit host;
                  keys = flake.nixosConfigurations.${"$"}{host}.config.users.users.admin.openssh.authorizedKeys.keys;
                })
                hosts
          ')

          while IFS= read -r row; do
            host=$(printf '%s' "$row" | jq -r '.host')
            key_count=$(printf '%s' "$row" | jq '.keys | length')
            [ "$key_count" -eq 4 ] || fail "expected four admin authorized keys on developer-access host $host, got: $key_count"

            for marker in \
              'flippos@inexen9' \
              'AAAAC3NzaC1lZDI1NTE5AAAAIAVt7FP3BCARMRyL791VauxIPd3t8nVm4A49VVpL9FUj' \
              'AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK' \
              'AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M'
            do
              if ! printf '%s' "$row" | jq -e --arg marker "$marker" '.keys | any(contains($marker))' >/dev/null; then
                fail "expected developer-access host $host to contain SSH key marker: $marker"
              fi
            done
          done < <(printf '%s' "$snapshot" | jq -c '.[]')
        '';
      }
      {
        name = "baseline-hosts-stay-on-root-admin-key-only";
        type = "script";
        script = ''
          ${ntlib.helpers.path [
            pkgs.coreutils
            pkgs.gnugrep
            pkgs.jq
            pkgs.nix
          ]}
          ${ntlib.helpers.scriptHelpers}

          snapshot=$(nix eval --json --impure --expr '
            let
              flake = builtins.getFlake "${flakeRef}";
              hosts = ${builtins.toJSON baselineHosts};
            in
              builtins.map
                (host: {
                  inherit host;
                  keys = flake.nixosConfigurations.${"$"}{host}.config.users.users.admin.openssh.authorizedKeys.keys;
                })
                hosts
          ')

          while IFS= read -r row; do
            host=$(printf '%s' "$row" | jq -r '.host')
            key_count=$(printf '%s' "$row" | jq '.keys | length')
            [ "$key_count" -eq 1 ] || fail "expected baseline host $host to keep exactly one admin authorized key, got: $key_count"

            if ! printf '%s' "$row" | jq -e '.keys | any(contains("AAAAC3NzaC1lZDI1NTE5AAAAIM7vvbgQtzi4GNeugHSuMyEke4MY0bSfoU7cBOnRYU8M"))' >/dev/null; then
              fail "expected baseline host $host to keep the root/admin SSH key"
            fi

            if printf '%s' "$row" | jq -e '.keys | any(contains("flippos@inexen9"))' >/dev/null; then
              fail "baseline host $host unexpectedly contains developer overlay SSH keys"
            fi
          done < <(printf '%s' "$snapshot" | jq -c '.[]')
        '';
      }
    ];
  };
}
