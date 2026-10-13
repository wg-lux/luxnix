#!/usr/bin/env bash
set -euo pipefail
umask 077
usage() {
  echo 'Usage: devenv shell enroll-reachable-hub-sites [--site gc-09] [--ask-become-pass] (interactive hidden prompts)' >&2
  exit 2
}
[[ -t 0 ]] || usage
site=''
prompt=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --site)
      [[ $# -ge 2 && -z "$site" && "$2" =~ ^gc-[0-9]+$ ]] || usage
      site="$2"
      shift 2
      ;;
    --ask-become-pass)
      [[ ${#prompt[@]} -eq 0 ]] || usage
      prompt=(--ask-become-pass)
      shift
      ;;
    *) usage ;;
  esac
done
scope=(--limit gs-02:active_clients)
if [[ -n "$site" ]]; then
  scope=(--limit "gs-02:$site" -e "fleet_enrollment_site=$site")
fi
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
case "$root" in
  /tmp|/tmp/*) echo 'ERROR: a durable reviewed checkout is required.' >&2; exit 2 ;;
esac
cd -- "$root"
# Only this reviewed inventory and its pinned SSH registry are used. Do not
# inherit an alternate config, cached tokens, or credential-bearing log setup.
unset VAULT_TOKEN ANSIBLE_LOG_PATH ANSIBLE_SSH_ARGS ANSIBLE_SSH_EXTRA_ARGS
export ANSIBLE_CONFIG="$root/conf/connectivity-ansible.cfg"
export ANSIBLE_HOST_KEY_CHECKING=True
export ANSIBLE_PIPELINING=True
export ANSIBLE_DEBUG=False
export ANSIBLE_DISPLAY_ARGS_TO_STDOUT=False
export ANSIBLE_REMOTE_TEMP=/dev/shm
export ANSIBLE_SSH_COMMON_ARGS="-o StrictHostKeyChecking=yes -o UserKnownHostsFile=$root/conf/ssh-host-keys/known_hosts -o GlobalKnownHostsFile=/dev/null -o ConnectTimeout=5"
bash scripts/run-secret-playbook.sh ansible/playbooks/enroll_reachable_hub_sites.yml \
  -i ansible/inventory/hosts.ini "${scope[@]}" \
  -e ansible_python_interpreter=/run/current-system/sw/bin/python3 \
  -e ansible_become_user=root "${prompt[@]}"
