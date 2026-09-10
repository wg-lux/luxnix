#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/monitor-lx-annotate-pipeline.sh [HOST] [options]
  scripts/monitor-lx-annotate-pipeline.sh --local [options]

Examples:
  scripts/monitor-lx-annotate-pipeline.sh gc-10
  scripts/monitor-lx-annotate-pipeline.sh gc-10 --since "2 hours ago" --lines 240
  scripts/monitor-lx-annotate-pipeline.sh gc-10 --follow
  scripts/monitor-lx-annotate-pipeline.sh --local --since "30 minutes ago"

Options:
  --since VALUE       journalctl time window. Default: "30 minutes ago"
  --lines N          lines to keep per journal section. Default: 160
  --redis-db N       Redis database used by Celery queues. Default: 1
  --follow, -f       after the snapshot, follow matching journal lines
  --local            force local execution instead of SSH dispatch
  --help, -h         show this help
EOF
}

services=(
  lx-annotate-manage.service
  lx-annotate-celery-pipeline-worker.service
  lx-annotate-celery-ffmpeg-worker.service
  lx-annotate-celery-frame-extraction-worker.service
  lx-annotate-celery-worker.service
  lx-annotate-celery-inference-worker.service
)

queues=(
  default
  maintenance
  pipeline
  ffmpeg_media
  frame_extraction
  inference
  llm_inference
  model_training
)

since="30 minutes ago"
lines=160
redis_db=1
follow=0

if [[ $# -gt 0 && "${1}" != --* && "${1}" != "." && "${1}" != "local" ]]; then
  host="${1}"
  shift
  current_hosts=(
    localhost
    127.0.0.1
    "$(hostname 2>/dev/null || true)"
    "$(hostname -s 2>/dev/null || true)"
    "$(hostname -f 2>/dev/null || true)"
  )
  for current_host in "${current_hosts[@]}"; do
    if [[ -n "${current_host}" && "${host}" == "${current_host}" ]]; then
      set -- --local "$@"
      host=""
      break
    fi
  done
fi

if [[ -n "${host:-}" ]]; then
  remote_command="bash -s --"
  remote_args=(--local "$@")
  for arg in "${remote_args[@]}"; do
    remote_command+=" $(printf '%q' "${arg}")"
  done
  exec ssh "${host}" "${remote_command}" < "${BASH_SOURCE[0]}"
fi

if [[ $# -gt 0 && ( "${1}" == "." || "${1}" == "local" ) ]]; then
  shift
fi

while [[ $# -gt 0 ]]; do
  case "${1}" in
    --local)
      shift
      ;;
    --since)
      since="${2:?--since requires a value}"
      shift 2
      ;;
    --since=*)
      since="${1#*=}"
      shift
      ;;
    --lines)
      lines="${2:?--lines requires a value}"
      shift 2
      ;;
    --lines=*)
      lines="${1#*=}"
      shift
      ;;
    --redis-db)
      redis_db="${2:?--redis-db requires a value}"
      shift 2
      ;;
    --redis-db=*)
      redis_db="${1#*=}"
      shift
      ;;
    --follow|-f)
      follow=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: ${1}" >&2
      usage >&2
      exit 2
      ;;
  esac
done

failure_pattern='error|failed|failure|traceback|exception|unsupportedoperation|integrity_lost|ffprobe|framecleaner|anonymiz|timeout|killed|oom|finalize_failure|content-hash|videometa|could not download|raised unexpected|runtimeerror|oserror'
pipeline_pattern='Task endoreg_db\.|process_upload_job|video_temporal_inference|frame_extraction|ffmpeg|anonymiz|VideoMeta|finalize|integrity|content-hash|could not download|UnsupportedOperation|raised unexpected|succeeded|received'

journal_args=()
for service in "${services[@]}"; do
  journal_args+=(-u "${service}")
done

section() {
  printf '\n=== %s ===\n' "$*"
}

run_or_note() {
  local binary="${1}"
  shift
  if command -v "${binary}" >/dev/null 2>&1; then
    "${binary}" "$@"
  else
    echo "${binary} not found"
  fi
}

section "snapshot"
printf 'host=%s\n' "$(hostname -f 2>/dev/null || hostname)"
printf 'time=%s\n' "$(date -Is)"
printf 'since=%s\n' "${since}"

section "installed package versions"
python_bin=""
if [[ -x /var/endoreg-service-user/lx-annotate-wheel/.venv/bin/python ]]; then
  python_bin=/var/endoreg-service-user/lx-annotate-wheel/.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  python_bin="$(command -v python3)"
fi

if [[ -n "${python_bin}" ]]; then
  "${python_bin}" - <<'PY' || true
from importlib import metadata

for package in ("lx-annotate", "endoreg-db", "lx-anonymizer"):
    try:
        print(f"{package}={metadata.version(package)}")
    except metadata.PackageNotFoundError:
        print(f"{package}=not-installed")

try:
    dist = metadata.distribution("endoreg-db")
    path = dist.locate_file("endoreg_db/utils/storage/files.py")
    text = path.read_text()
    has_seek_guard = "seekable" in text and "UnsupportedOperation" in text
    print(f"endoreg-db storage files.py={path}")
    print(f"ensure_local_file_seekable_guard={has_seek_guard}")
except Exception as exc:
    print(f"endoreg-db storage files.py=unavailable ({exc})")
PY
else
  echo "python not found"
fi

section "failed systemd units"
systemctl --no-pager --plain --failed || true

section "lx-annotate service states"
for service in "${services[@]}"; do
  printf '%-58s %s\n' "${service}" "$(systemctl is-active "${service}" 2>/dev/null || true)"
done

section "redis queue lengths db${redis_db}"
if command -v redis-cli >/dev/null 2>&1; then
  for queue in "${queues[@]}"; do
    printf '%-18s %s\n' "${queue}" "$(redis-cli -n "${redis_db}" llen "${queue}" 2>/dev/null || echo unavailable)"
  done
else
  echo "redis-cli not found"
fi

section "celery task failure summary"
journalctl "${journal_args[@]}" --since "${since}" --no-pager -o short-iso 2>/dev/null \
  | grep -Eo 'Task [A-Za-z0-9_.-]+\[[^]]+\] raised unexpected' \
  | sed -E 's/\[[^]]+\]//' \
  | sort \
  | uniq -c \
  | sort -nr \
  || true

section "affected media identifiers"
journalctl "${journal_args[@]}" --since "${since}" --no-pager -o short-iso 2>/dev/null \
  | grep -Eo 'sensitive_videos/[[:alnum:]_.-]+|upload_jobs/[[:alnum:]_/.-]+|video [0-9a-f]{64}|content_hash[_a-z]*[=: ][0-9a-f]{64}' \
  | sort \
  | uniq -c \
  | sort -nr \
  | head -80 \
  || true

section "failure lines by service"
for service in "${services[@]}"; do
  printf '\n--- %s ---\n' "${service}"
  journalctl -u "${service}" --since "${since}" --no-pager -o short-iso 2>/dev/null \
    | grep -Ei "${failure_pattern}" \
    | tail -n "${lines}" \
    || true
done

section "recent pipeline task markers"
journalctl "${journal_args[@]}" --since "${since}" --no-pager -o short-iso 2>/dev/null \
  | grep -Ei "${pipeline_pattern}" \
  | tail -n "${lines}" \
  || true

if [[ "${follow}" -eq 1 ]]; then
  section "following matching journal lines"
  journalctl "${journal_args[@]}" -f -o short-iso 2>/dev/null \
    | grep -Ei --line-buffered "${failure_pattern}|${pipeline_pattern}" \
    || true
fi
