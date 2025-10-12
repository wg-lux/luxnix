#!/usr/bin/env bash
set -euo pipefail

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

mkdir -p "${logs_dir}"
log_file="${logs_dir}/connectivity-$(date +%Y%m%d-%H%M%S).log"

# Determine the limit target. Default to 'all' if the first argument is missing or starts with '-'.
target="all"
extra_args=()

if [[ $# -gt 0 && ${1} != --* ]]; then
  target="${1}"
  shift
fi

if [[ $# -gt 0 ]]; then
  extra_args=("$@")
fi

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
if [[ ${#extra_args[@]} -gt 0 ]]; then
  cmd+=("${extra_args[@]}")
fi

echo "Running: ${cmd[*]}"
printf 'Running: %s\n\n' "${cmd[*]}" > "${log_file}"


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
