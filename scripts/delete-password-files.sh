#!/bin/sh
# Delete password files on the local machine. Destructive and not recoverable.
#
#   scripts/delete-password-files.sh --scope unused [--apply] [root...]
#   scripts/delete-password-files.sh --scope all    [--apply] [root...]
#
#   --scope unused  Only files with no confirmed consumer.
#   --scope all     Also the active account hashes and service passwords. The next
#                   NixOS activation is refused until the account hashes are
#                   restored, and services fail once their password file is gone.
#   --apply         Delete after a typed confirmation. Without it, only list files.
#   root...         Directories to search; defaults to /.
#
# Matching is on file paths, never file contents, so code and configuration that
# merely mention a password path are kept. Disk and vault keys are never matched:
# ~/.lxv.key, ~/.lxv/storage-recovery, ~/.lxv/openbao-local, the boot passphrase
# state and the OpenBao seal. Run with sudo to reach root-only directories.
set -u

UNUSED='/etc/user-passwords/[^/]+$|/SCRT_roles_system_password_(nextcloud_host_minio_credentials|nginx_host_password|postgres_host_(test|main)_password)$|/SCRT_client_user_password$|/SCRT_groups_system_password_[^/]+$|/\.lxv/deploy/gc-03/SCRT_[^/]*password[^/]*$'

ACTIVE='/luxnix-account/(admin|client)-password\.hash$|/SCRT_[^/]*(password|credentials)[^/]*$|/endoregDbLocal\.password$|/nextcloud-admin-pass$|/db-password$|/etc/secrets/vault/smtp_pwd$'

KEEP='/\.lxv/(storage-recovery|openbao-local)/|/\.lxv\.key$|/luxnix-boot-passphrase/|/seal-passphrase\.json$'

usage() {
  echo "usage: $0 --scope {unused|all} [--apply] [root...]" >&2
  exit 2
}

scope=""
apply=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --scope)
      [ "$#" -ge 2 ] || usage
      scope="$2"
      shift 2
      ;;
    --apply)
      apply=1
      shift
      ;;
    --*) usage ;;
    *) break ;;
  esac
done

case "$scope" in
  unused) pattern="$UNUSED" ;;
  all) pattern="$UNUSED|$ACTIVE" ;;
  *) usage ;;
esac

[ "$#" -gt 0 ] || set -- /

if [ "$(id -u)" -ne 0 ]; then
  echo "NOTE: not running as root; unreadable directories are skipped." >&2
fi

list="$(mktemp)" || exit 1
trap 'rm -f "$list"' EXIT

find "$@" \( -path /proc -o -path /sys -o -path /dev -o -path /nix/store -o -name .git \) -prune -o \
  \( -type f -o -type l \) -print 2>/dev/null |
  grep -E "$pattern" | grep -vE "$KEEP" > "$list"

count="$(wc -l < "$list" | tr -d ' ')"
if [ "$count" -eq 0 ]; then
  echo "No matching files for scope '$scope'."
  exit 0
fi

cat "$list"
echo "--- $count file(s) match scope '$scope'."

if [ "$apply" -ne 1 ]; then
  echo "Dry run: nothing was deleted. Add --apply to delete."
  exit 0
fi

phrase="DELETE $count FILES ON $(hostname)"
echo "This cannot be undone. Confirm that independent copies exist first."
printf 'Type "%s" to continue: ' "$phrase"
if ! read -r answer < /dev/tty; then
  echo "ERROR: confirmation needs a terminal; nothing was deleted." >&2
  exit 1
fi
if [ "$answer" != "$phrase" ]; then
  echo "Confirmation did not match; nothing was deleted." >&2
  exit 1
fi

failed=0
while IFS= read -r file; do
  if rm -f -- "$file"; then
    echo "deleted: $file"
  else
    failed=$((failed + 1))
  fi
done < "$list"

if [ "$failed" -ne 0 ]; then
  echo "ERROR: $failed file(s) could not be deleted." >&2
  exit 1
fi
