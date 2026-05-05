{
  pkgs,
  ntlib,
  repoRoot,
  ...
}: let
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
in {
  suites."ssh host contracts" = {
    pos = __curPos;
    tests = [
      {
        name = "all-configured-linux-hosts-keep-secure-ssh-baseline";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.coreutils pkgs.gnugrep pkgs.jq pkgs.nix]}
          ${ntlib.helpers.scriptHelpers}

          snapshot=$(nix eval --json --impure --expr '
            let
              flake = builtins.getFlake "${flakeRef}";
              hosts = ${builtins.toJSON linuxHosts};
            in
              builtins.map
                (host: {
                  inherit host;
                  enable = flake.nixosConfigurations.${"$"}{host}.config.services.openssh.enable;
                  passwordAuth = flake.nixosConfigurations.${"$"}{host}.config.services.openssh.settings.PasswordAuthentication;
                  ports = flake.nixosConfigurations.${"$"}{host}.config.services.openssh.ports;
                  keyCount = builtins.length flake.nixosConfigurations.${"$"}{host}.config.users.users.admin.openssh.authorizedKeys.keys;
                })
                hosts
          ')

          while IFS=$'\t' read -r host enable password_auth ports_ok key_count; do
            [ "$enable" = "true" ] || fail "expected SSH to be enabled for $host, got: $enable"
            [ "$password_auth" = "false" ] || fail "expected PasswordAuthentication=false for $host, got: $password_auth"
            [ "$ports_ok" = "true" ] || fail "expected SSH ports [22] for $host"
            [ "$key_count" -ge 1 ] || fail "expected at least one admin authorized key for $host"
          done < <(
            printf '%s' "$snapshot" | jq -r '.[] | [.host, (.enable|tostring), (.passwordAuth|tostring), ((.ports == [22])|tostring), (.keyCount|tostring)] | @tsv'
          )
        '';
      }
      {
        name = "developer-access-hosts-keep-explicit-ssh-overlays";
        type = "script";
        script = ''
          ${ntlib.helpers.path [pkgs.coreutils pkgs.gnugrep pkgs.jq pkgs.nix]}
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
              'AAAAC3NzaC1lZDI1NTE5AAAAIDBJcYjGNIwOUs+KG8TbBxPWtJFEqni0p+1J5Yz++Aos' \
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
          ${ntlib.helpers.path [pkgs.coreutils pkgs.gnugrep pkgs.jq pkgs.nix]}
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
