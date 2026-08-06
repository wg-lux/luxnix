#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: check-connectivity.sh <inventory-host-or-group> [ansible-playbook arguments...]

Checks SSH connectivity and remote command execution for one explicit inventory
host or group. Use "all" explicitly when a full-inventory check is intended.
EOF
}

if [[ $# -eq 0 ]]; then
  echo "ERROR: an inventory host or group is required; refusing to default to all." >&2
  usage >&2
  exit 2
fi

case "$1" in
  -h | --help)
    usage
    exit 0
    ;;
  -*)
    echo "ERROR: the first argument must be an inventory host or group, not an option." >&2
    usage >&2
    exit 2
    ;;
esac

target="$1"
shift

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
inventory_file="${project_root}/ansible/inventory/hosts.ini"
playbook_file="${project_root}/ansible/playbooks/connectivity-check.yml"
logs_dir="${project_root}/logs"

if [[ ! -f "${playbook_file}" ]]; then
  echo "Playbook not found at ${playbook_file}" >&2
  exit 1
fi

if [[ ! -f "${inventory_file}" ]]; then
  echo "Inventory not found at ${inventory_file}" >&2
  exit 1
fi

install -d -m 0700 "${logs_dir}"
log_file="${logs_dir}/connectivity-$(date +%Y%m%d-%H%M%S)-$$.log"

ansible_config="${project_root}/ansible.cfg"
if [[ -L "${ansible_config}" && ! -e "${ansible_config}" ]]; then
  # Fallback to template if the ansible.cfg symlink isn't resolved.
  fallback_cfg="${project_root}/conf/TEMPLATE_ansible.cfg"
  if [[ -f "${fallback_cfg}" ]]; then
    ansible_config="${fallback_cfg}"
  else
    ansible_config=""
  fi
fi

cmd=(ansible-playbook "${playbook_file}" -i "${inventory_file}" --limit "${target}")
if [[ $# -gt 0 ]]; then
  cmd+=("$@")
fi

echo "Running connectivity check for inventory target: ${target}"
printf 'Connectivity check target: %s\n\n' "${target}" > "${log_file}"

set +e
if [[ -n "${ansible_config}" && -f "${ansible_config}" ]]; then
  ANSIBLE_CONFIG="${ansible_config}" "${cmd[@]}" 2>&1 | tee -a "${log_file}"
  status=${PIPESTATUS[0]}
else
  "${cmd[@]}" 2>&1 | tee -a "${log_file}"
  status=${PIPESTATUS[0]}
fi
set -e

echo "Log written to ${log_file}"
exit "${status}"
