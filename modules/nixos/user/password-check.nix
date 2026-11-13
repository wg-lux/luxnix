# Shared read-only gate for declarative Linux account credentials.
{
  lib,
  pkgs,
  account,
  passwordFile,
}:
''
  # Literal account name, not command substitution.
  # shellcheck disable=SC2209
  account=${lib.escapeShellArg account}
  password_file=${lib.escapeShellArg passwordFile}
  if [ ! -f "$password_file" ] || [ ! -s "$password_file" ]; then
    echo "ERROR: password hash file is missing or empty for $account. Refusing activation; use explicit account recovery." >&2
    exit 1
  fi
  case "$(${pkgs.coreutils}/bin/stat -Lc '%u:%a' -- "$password_file")" in
    0:400|0:600) ;;
    *) echo "ERROR: password hash must be root-owned with mode 0400 or 0600." >&2; exit 1 ;;
  esac
  if ! ${pkgs.gnugrep}/bin/grep -qxE '[$]6[$](rounds=[0-9]+[$])?[./A-Za-z0-9]{1,16}[$][./A-Za-z0-9]{86}|[$]y[$][./A-Za-z0-9]+[$][./A-Za-z0-9]+[$][./A-Za-z0-9]{43}' "$password_file" ||
     [ "$(${pkgs.gawk}/bin/awk 'END { print NR }' "$password_file")" -ne 1 ]; then
    echo "ERROR: password file must contain exactly one SHA-512 crypt or yescrypt hash." >&2
    exit 1
  fi
  if [ "$(${pkgs.coreutils}/bin/head -n 1 "$password_file" | ${pkgs.coreutils}/bin/tr -d '\n' | ${pkgs.coreutils}/bin/sha256sum | ${pkgs.coreutils}/bin/cut -d ' ' -f 1)" = a396e38d2c16276942366260dfc8e88ccef88e5df8915d50e688aca7e1502bba ]; then
    echo "ERROR: the retired shared admin password is prohibited." >&2
    exit 1
  fi
  # NixOS otherwise reapplies hashedPasswordFile even for an existing account.
  # New accounts may consume provisioned credentials; changes require rotation
  # to update the live account explicitly before the next activation.
  if shadow_entry="$(${pkgs.getent}/bin/getent -s files shadow "$account")"; then
    current_hash="''${shadow_entry#*:}"
    current_hash="''${current_hash%%:*}"
    configured_hash="$(${pkgs.coreutils}/bin/cat "$password_file")"
    if [ "$configured_hash" != "$current_hash" ]; then
      echo "ERROR: refusing automatic password change for $account. Explicitly rotate with confirmation or password entry; keep the live account and its persistent hash consistent." >&2
      exit 1
    fi
  else
    lookup_status=$?
    if [ "$lookup_status" -ne 2 ]; then
      echo "ERROR: cannot read the local shadow database." >&2
      exit 1
    fi
    if ${pkgs.getent}/bin/getent -s files passwd "$account" >/dev/null; then
      echo "ERROR: existing account has no readable shadow entry; refusing activation." >&2
      exit 1
    else
      lookup_status=$?
      if [ "$lookup_status" -ne 2 ]; then
        echo "ERROR: cannot establish whether the local account exists." >&2
        exit 1
      fi
    fi
  fi
  unset shadow_entry current_hash configured_hash
''
