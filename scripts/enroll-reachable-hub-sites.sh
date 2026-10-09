#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ ! -t 0 ]] || [[ $# -gt 0 ]]; then
  echo 'Usage: devenv shell enroll-reachable-hub-sites (interactive token prompt, no arguments)' >&2
  exit 2
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
  -i ansible/inventory/hosts.ini --limit 'gs-02:active_clients' \
  -e ansible_python_interpreter=/run/current-system/sw/bin/python3 \
  -e ansible_become_user=root
