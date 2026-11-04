#!/usr/bin/env bash
set -euo pipefail
umask 077
usage() {
  cat <<'EOF'
Usage: devenv shell enroll-reachable-hub-sites [--site gc-09] [--ask-sudo-password]

Run as the controller's normal administrator, from a reviewed LuxNix checkout.
--site HOST           Enroll one configured site and use gs-02 as its hub.
                      Without this option, consider every configured active site.
--ask-sudo-password   Ask privately for the Linux login account's sudo password
                      separately on each reachable site and on gs-02.
                      Different hosts may have different passwords.
--ask-become-pass     Legacy option: Ansible asks once for a shared sudo password.
--help               Show this help without connecting to any host.

SSH keys and verified host keys must already work from this controller to each
target, including gs-02. A sudo password does not authenticate SSH or Vault.
After access checks, enter the short-lived Vault enrollment token at its hidden
prompt. Vault must already be initialized and unsealed. An unseal share is not
an enrollment token. See docs/vault-hub-machine-enrollment.md for prerequisites.
EOF
  exit "${1:-2}"
}
site=''
prompt=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --site)
      [[ $# -ge 2 && -z "$site" && "$2" =~ ^gc-[0-9]+$ ]] || usage
      site="$2"
      shift 2
      ;;
    --ask-sudo-password)
      [[ ${#prompt[@]} -eq 0 ]] || usage
      prompt=(-e fleet_prompt_sudo_password=true)
      shift
      ;;
    --ask-become-pass)
      [[ ${#prompt[@]} -eq 0 ]] || usage
      prompt=(--ask-become-pass)
      shift
      ;;
    --help|-h) usage 0 ;;
    *) usage ;;
  esac
done
[[ -t 0 ]] || usage
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
