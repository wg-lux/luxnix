#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: luxnix-vault-prepare-server-rebuild --recipient age1... --output-directory /secure/path" >&2
}

recipient=""
output_directory=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --recipient) recipient="${2:-}"; shift 2 ;;
    --output-directory) output_directory="${2:-}"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: run this command as root on the Vault server." >&2
  exit 1
fi
if [[ "$(hostname)" != "$EXPECTED_HOSTNAME" ]]; then
  echo "ERROR: expected host $EXPECTED_HOSTNAME; refusing to archive another machine." >&2
  exit 1
fi
if [[ ! "$recipient" =~ ^age1[0-9a-z]+$ ]] || [[ -z "$output_directory" ]]; then
  usage
  exit 2
fi
if [[ "$output_directory" != /* ]] || [[ ! -d "$output_directory" ]]; then
  echo "ERROR: output directory must be an existing absolute directory." >&2
  exit 2
fi
output_directory="$(realpath "$output_directory")"
case "$output_directory/" in
  "$VAULT_STORAGE_PATH/"*|"$VAULT_TLS_STATE_DIRECTORY/"*|/etc/secrets/*)
    echo "ERROR: backup destination must be outside Vault and secret state directories." >&2
    exit 2
    ;;
esac
directory_mode="$(stat -c '%a' "$output_directory")"
if (( (8#$directory_mode & 8#077) != 0 )); then
  echo "ERROR: output directory must not be accessible by group or other users (mode 0700 or stricter)." >&2
  exit 1
fi
if systemctl is-active --quiet vault.service; then
  echo "ERROR: vault.service is active. Stop it during an approved outage before taking the archive." >&2
  exit 1
fi
if [[ ! -d "$VAULT_STORAGE_PATH" ]] || [[ ! -f "$VAULT_TLS_CA_FILE" ]]; then
  echo "ERROR: required Vault Raft or TLS CA state is missing." >&2
  exit 1
fi

umask 077
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$output_directory/gs-02-vault-pre-rebuild-$timestamp.tar.age"
manifest="$archive.sha256"
if [[ -e "$archive" || -e "$manifest" ]]; then
  echo "ERROR: backup output already exists." >&2
  exit 1
fi

paths=("${VAULT_STORAGE_PATH#/}" "${VAULT_TLS_STATE_DIRECTORY#/}")
if [[ -d /etc/secrets/vault/hub-pki ]]; then
  paths+=("etc/secrets/vault/hub-pki")
fi

temporary="$archive.partial"
trap 'rm -f "$temporary"' EXIT
tar --xattrs --acls --numeric-owner -C / -cf - "${paths[@]}" \
  | age --recipient "$recipient" --output "$temporary"
chmod 0600 "$temporary"
mv "$temporary" "$archive"
(
  cd "$output_directory"
  sha256sum "$(basename "$archive")"
) > "$manifest"
chmod 0600 "$manifest"
trap - EXIT

echo "Encrypted pre-rebuild archive created: $archive"
echo "Checksum manifest created: $manifest"
echo "Verify decryption on a separate trusted machine before authorizing any reset."
