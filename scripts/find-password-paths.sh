#!/usr/bin/env bash
# Read-only search for password storage paths and the code that references them.
#
#   scripts/find-password-paths.sh repo                 Matching lines in tracked and untracked repository files
#   scripts/find-password-paths.sh names [root...]      Files on disk named like a password file
#   scripts/find-password-paths.sh content [root...]    Files on disk that mention a password path
#   scripts/find-password-paths.sh closure              Current NixOS system closure files that mention one
#
# Filesystem modes print paths only, never file contents, because the scanned
# files can themselves be secrets. Run them with sudo to include root-only
# directories; without it those directories are skipped.
set -uo pipefail

# Paths and names with a confirmed consumer.
ACTIVE='luxnix-account/(admin|client)-password\.hash|SCRT_local_password_(admin_password(_hash)?|maintenance_password)|SCRT_client_user_password_hash|endoregDbLocal\.password|SCRT_roles_system_password_(keycloak_host_password|nextcloud_host_password|nextcloud_host_garage_credentials)|nextcloud-admin-pass|\.lxv(\.key|/secrets|/deploy|/admin-rotations)'

# Candidates for retirement; a match here is what still needs reviewing.
UNUSED='/etc/user-passwords|(admin|dev-01|user)_hashed|SCRT_roles_system_password_(nextcloud_host_minio_credentials|nginx_host_password|postgres_host_(test|main)_password)|nextcloud_minio_credentials|SCRT_client_user_password([^_]|$)|SCRT_groups_system_password_|\.lxv/deploy/gc-03|restic_password|plausible_admin_password|photoprism_admin_password|paperless_pass|gitea_smtp_password'

# Consumers not yet traced.
UNDETERMINED='smtp_pwd|secrets/user-passwords|secrets/archived|luxnix-boot-passphrase|seal-passphrase\.json|\.lxv/(storage-recovery|openbao-local)'

# Variables and options that build these paths at runtime, so literal matches miss them.
INDIRECT='admin_password_(hashed_)?filename|maintenance(_password_filename|SecretFileName)|postgres_host_(main|test)_password_filename|(nginx|keycloak|nextcloud)_host_password_filename|adminPassword(Hashed)?File|applicationPasswordFile|dbPasswordfile|passwordFilePath|garageCredentialsFilePath|hashedPasswordFile|lx_vault_dir(_src)?|lx_vault_host_deploy_dir'

ALL="$ACTIVE|$UNUSED|$UNDETERMINED"

NAMES='.*/(SCRT_[^/]*(password|credentials)[^/]*|[^/]*-password\.hash|[^/]*_hashed|endoregDbLocal\.password|db-password|nextcloud-admin-pass|smtp_pwd|seal-passphrase\.json|cryptroot\.json|\.lxv\.key)'

warn_if_unprivileged() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "NOTE: not running as root; unreadable directories are skipped." >&2
  fi
}

search_repo() {
  local root group pattern
  root="$(git rev-parse --show-toplevel)" || exit 2
  cd "$root" || exit 2
  for group in ACTIVE UNUSED UNDETERMINED INDIRECT; do
    pattern="${!group}"
    echo "=== $group"
    git grep --untracked -nIE "$pattern" -- ':!scripts/find-password-paths.sh' | cut -c1-200
  done
}

search_names() {
  warn_if_unprivileged
  [ "$#" -gt 0 ] || set -- /
  find "$@" \( -path /proc -o -path /sys -o -path /dev -o -path /nix/store \) -prune -o \
    -type f -regextype posix-extended -regex "$NAMES" -print 2>/dev/null
}

search_content() {
  warn_if_unprivileged
  [ "$#" -gt 0 ] || set -- /etc /home /root /var/lib
  grep -rIlE \
    --exclude-dir=.cache --exclude-dir=.git --exclude-dir=.direnv --exclude-dir=.devenv \
    --exclude-dir=node_modules --exclude-dir=containers --exclude-dir=docker --exclude-dir=postgresql \
    -- "$ALL" "$@" 2>/dev/null
}

search_closure() {
  nix-store -qR /run/current-system | xargs -r -d '\n' grep -rIlE -- "$ALL" 2>/dev/null
}

mode="${1:-}"
[ "$#" -eq 0 ] || shift
case "$mode" in
  repo) search_repo ;;
  names) search_names "$@" ;;
  content) search_content "$@" ;;
  closure) search_closure ;;
  *)
    echo "usage: $0 {repo|names [root...]|content [root...]|closure}" >&2
    exit 2
    ;;
esac
