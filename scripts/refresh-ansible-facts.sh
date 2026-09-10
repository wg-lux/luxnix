#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/refresh-ansible-facts.sh [--strict] [--config PATH]
       scripts/refresh-ansible-facts.sh [--strict] --ansible-root PATH

Refresh <paths.ansible_root>/cmdb/*.json from the configured Ansible inventory.
Each valid host response atomically replaces only that host's local snapshot.
Failed hosts keep their last-known-good snapshot. By default, a partial refresh
succeeds when at least one host was refreshed; --strict fails on any stale host.

--config resolves paths.ansible_root from the central Autoconf configuration.
--ansible-root is an explicit override for standalone and test environments.

The snapshots are sensitive Autoconf inputs and are excluded from Git.
EOF
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"
config_file=""
config_explicit=false
ansible_root=""
strict=false

while (( $# > 0 )); do
  case "$1" in
    --strict)
      strict=true
      shift
      ;;
    --config)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      config_file="$2"
      config_explicit=true
      shift 2
      ;;
    --ansible-root)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      ansible_root="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$config_explicit" == true && -n "$ansible_root" ]]; then
  echo "--config and --ansible-root are mutually exclusive" >&2
  exit 2
fi

required_commands=(ansible jq)
if [[ -z "$ansible_root" ]]; then
  required_commands+=(python)
fi
for command_name in "${required_commands[@]}"; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

if [[ -z "$ansible_root" ]]; then
  config_args=()
  if [[ "$config_explicit" == true ]]; then
    config_args=(--config "$config_file")
  fi
  ansible_root="$(
    python "$repo_root/scripts/autoconf-pipeline.py" \
      "${config_args[@]}" \
      --print-option paths.ansible_root
  )"
fi
inventory_file="$ansible_root/inventory/hosts.ini"
facts_dir="$ansible_root/cmdb"

if [[ ! -f "$inventory_file" ]]; then
  echo "Ansible inventory not found: $inventory_file" >&2
  exit 1
fi

umask 077
staging_root="$(mktemp -d "$ansible_root/.cmdb-refresh.XXXXXX")"
raw_dir="$staging_root/raw"
formatted_dir="$staging_root/formatted"
local_temp_dir="$staging_root/ansible-local"
collector_log="$staging_root/ansible.log"
host_list="$staging_root/hosts.txt"
mkdir -p "$raw_dir" "$formatted_dir" "$local_temp_dir"

cleanup() {
  local exit_status=$?

  rm -rf -- "$staging_root"
  exit "$exit_status"
}
trap cleanup EXIT

if ! ANSIBLE_LOCAL_TEMP="$local_temp_dir" \
  ansible all -i "$inventory_file" --list-hosts >"$host_list" 2>"$collector_log"; then
  echo "Could not resolve hosts from $inventory_file; no snapshots were changed." >&2
  exit 1
fi

expected_hosts=()
while IFS= read -r host_name; do
  host_name="${host_name#"${host_name%%[![:space:]]*}"}"
  host_name="${host_name%"${host_name##*[![:space:]]}"}"
  [[ -z "$host_name" ]] && continue
  if [[ ! "$host_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "Unsafe inventory hostname rejected: $host_name" >&2
    exit 1
  fi
  expected_hosts+=("$host_name")
done < <(tail -n +2 "$host_list")

if (( ${#expected_hosts[@]} == 0 )); then
  echo "Inventory contains no hosts; no snapshots were changed." >&2
  exit 1
fi

echo "Collecting facts for ${#expected_hosts[@]} inventory hosts..."
set +e
ANSIBLE_LOCAL_TEMP="$local_temp_dir" \
  ansible all -i "$inventory_file" -m setup --tree "$raw_dir" \
  >>"$collector_log" 2>&1
collector_status=$?
set -e

shopt -s nullglob
refreshed_hosts=()
stale_hosts=()

for host_name in "${expected_hosts[@]}"; do
  raw_file="$raw_dir/$host_name"
  [[ -f "$raw_file" ]] || raw_file="$raw_dir/$host_name.json"

  if [[ ! -f "$raw_file" ]] || ! jq --arg host "$host_name" '
    def valid_result:
      type == "object"
      and (.ansible_facts | type == "object")
      and ((.failed // false) | not);

    if valid_result then
      {($host): [.]}
    elif type == "object"
      and (.[$host] | type == "array")
      and (.[$host] | length == 1)
      and (.[$host][0] | valid_result)
    then
      .
    else
      error("invalid Ansible setup response")
    end
  ' "$raw_file" >"$formatted_dir/$host_name.json" 2>/dev/null; then
    stale_hosts+=("$host_name")
    rm -f -- "$formatted_dir/$host_name.json"
    continue
  fi

  refreshed_hosts+=("$host_name")
done

mkdir -p "$facts_dir"
chmod 700 "$facts_dir"
for host_name in "${refreshed_hosts[@]}"; do
  chmod 600 "$formatted_dir/$host_name.json"
  mv -f -- "$formatted_dir/$host_name.json" "$facts_dir/$host_name.json"
done

echo "Refreshed (${#refreshed_hosts[@]}): ${refreshed_hosts[*]:-(none)}"
if (( ${#stale_hosts[@]} > 0 )); then
  echo "Stale or missing (${#stale_hosts[@]}): ${stale_hosts[*]}" >&2
  for host_name in "${stale_hosts[@]}"; do
    if [[ -f "$facts_dir/$host_name.json" ]]; then
      echo "  $host_name: retained last-known-good snapshot" >&2
    else
      echo "  $host_name: no valid snapshot available" >&2
    fi
  done
fi

if (( collector_status != 0 )); then
  echo "Ansible reported collection failures (exit $collector_status); details were not printed or retained." >&2
fi

if (( ${#refreshed_hosts[@]} == 0 )); then
  echo "No host was refreshed; existing snapshots were preserved." >&2
  exit 1
fi

if [[ "$strict" == true ]] && (( ${#stale_hosts[@]} > 0 || collector_status != 0 )); then
  exit 1
fi
