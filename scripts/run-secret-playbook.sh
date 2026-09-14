#!/usr/bin/env bash
set -euo pipefail
umask 077

# Ansible detaches controller workers from /dev/tty. Pass the original terminal
# device explicitly; never accept an inherited terminal override or piped yes.
if [[ "${1:-}" == *rotate_admin_passwords.yml ]]; then
  if [[ ! -t 0 ]]; then
    echo 'ERROR: admin rotation requires an interactive terminal.' >&2
    exit 2
  fi
  LUXNIX_ROTATION_TTY="$(tty)"
  export LUXNIX_ROTATION_TTY
fi

# Ansible copy/content stages plaintext. Confine controller temporaries to
# private tmpfs and clean them on every ordinary exit, including a failed run.
runtime_directory="${LUXNIX_SECRET_RUNTIME_DIR:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}}"
if [[ -L "$runtime_directory" || ! -d "$runtime_directory" ]] ||
   [[ "$(stat -c %u "$runtime_directory")" != "$(id -u)" ]] ||
   [[ "$(stat -c %a "$runtime_directory")" != 700 ]] ||
   [[ "$(findmnt -n -o FSTYPE --target "$runtime_directory")" != tmpfs ]]; then
  echo 'ERROR: secret delivery requires a private mode-0700 runtime directory on tmpfs.' >&2
  exit 2
fi
temporary="$(mktemp -d "$runtime_directory/luxnix-secret-playbook.XXXXXX")"
trap 'rm -rf -- "$temporary"' EXIT
script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_LOCAL_TEMP="$temporary" ANSIBLE_HOST_KEY_CHECKING=True \
  bash "$script_directory/run-ansible-playbook.sh" "$@"
