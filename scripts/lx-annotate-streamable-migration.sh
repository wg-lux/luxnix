#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  lx-annotate-streamable-migration <host> [migrate_video_streamable_storage args...]

Examples:
  lx-annotate-streamable-migration gc-10 --video-id 34 --processed-only
  lx-annotate-streamable-migration gc-10 --dry-run --processed-only

This runs the deployed lx-annotate Django streamable migration helper on the
target host under endoreg-service-user. The target command rewrites streamable
artifacts through the application storage/decryption layer and atomically
replaces invalid encrypted streamable files.
EOF
}

if [[ $# -eq 0 ]]; then
  echo "ERROR: a target host is required." >&2
  usage >&2
  exit 2
fi

case "$1" in
  -h | --help)
    usage
    exit 0
    ;;
  -*)
    echo "ERROR: the first argument must be a target host, not a migration option." >&2
    usage >&2
    exit 2
    ;;
esac

target_host="$1"
shift

exec ssh -t "$target_host" \
  sudo -u endoreg-service-user -g endoreg-service \
  /run/current-system/sw/bin/bash -lc \
  'exec /run/current-system/sw/bin/lx-annotate-migrate-video-streamable-storage "$@"' \
  lx-annotate-streamable-migration "$@"
