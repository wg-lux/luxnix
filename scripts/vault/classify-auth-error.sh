#!/usr/bin/env bash
set -euo pipefail

if (($# != 1)); then
  echo "Usage: luxnix-vault-classify-auth-error <vault-stderr-file>" >&2
  exit 2
fi

error_file="$1"
if [[ ! -r "$error_file" ]]; then
  echo "vault-error"
  exit 0
fi

if grep -Eqi \
  'x509:|certificate signed by unknown authority|certificate verify failed' \
  "$error_file"; then
  echo "tls-trust-failed"
elif grep -Eqi 'Vault is sealed' "$error_file"; then
  echo "vault-sealed"
elif grep -Eqi \
  'connection refused|no such host|network is unreachable|i/o timeout|context deadline exceeded|client\.timeout|temporary failure in name resolution|dial tcp|connection reset|unexpected EOF' \
  "$error_file"; then
  echo "vault-unreachable"
elif grep -Eqi \
  'permission denied|invalid role|invalid secret|invalid role or secret|Code: (400|401|403)' \
  "$error_file"; then
  echo "auth-rejected"
else
  echo "vault-error"
fi
