#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Internal usage: run-ansible-playbook.sh <playbook> --limit <host-or-group> [arguments...]

Runs one repository playbook only when the caller supplies an explicit Ansible
inventory limit. Use "--limit all" deliberately for a full-inventory run.
EOF
}

if [[ $# -eq 0 ]]; then
  echo "ERROR: an Ansible playbook path is required." >&2
  usage >&2
  exit 2
fi

playbook="$1"
shift

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
if [[ "${playbook}" != /* ]]; then
  playbook_path="${project_root}/${playbook}"
else
  playbook_path="${playbook}"
fi

if [[ ! -f "${playbook_path}" ]]; then
  echo "ERROR: Ansible playbook not found: ${playbook}" >&2
  exit 2
fi

arguments=("$@")
has_limit=false
index=0
while ((index < ${#arguments[@]})); do
  argument="${arguments[index]}"
  case "${argument}" in
    -h | --help)
      has_limit=true
      ;;
    -l | --limit)
      value_index=$((index + 1))
      if ((value_index >= ${#arguments[@]})) ||
        [[ -z "${arguments[value_index]}" || "${arguments[value_index]}" == -* ]]; then
        echo "ERROR: ${argument} requires a non-empty host or group." >&2
        exit 2
      fi
      has_limit=true
      index="${value_index}"
      ;;
    --limit=*)
      if [[ -z "${argument#--limit=}" ]]; then
        echo "ERROR: --limit requires a non-empty host or group." >&2
        exit 2
      fi
      has_limit=true
      ;;
    -l?*)
      has_limit=true
      ;;
  esac
  index=$((index + 1))
done

if [[ "${has_limit}" != true ]]; then
  echo "ERROR: an explicit --limit <host-or-group> is required;" \
    "refusing to target the full inventory implicitly." >&2
  usage >&2
  exit 2
fi

uv_bin="${LUXNIX_UV_BIN:-uv}"
cd -- "${project_root}"
exec "${uv_bin}" run ansible-playbook "${playbook}" "${arguments[@]}"
