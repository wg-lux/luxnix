#!/usr/bin/env bash
set -euo pipefail
umask 077

usage() {
  cat <<'EOF'
Usage: sync-site-policies.sh [OPTIONS]

Required:
  --node NAME              Repeatable site node identifier (for example: gc_02)

Optional:
  --nodes-file FILE        Read one node per line OR a yaml manifest (nodes/policy keys)
  --environment NAME       Policy suffix/environment (default: intern)
  --policy-prefix NAME     Policy name prefix (default: lx-hub-site)
  --pki-mount NAME        PKI mount name (default: lx-hub-pki)
  --secrets-mount NAME    Secrets mount name (default: lx-hub-secrets)
  --out-dir PATH           Write generated policies to a local directory as .hcl files.
  --dry-run                Generate and print policy content without writing to Vault.
  --help                   Show this help text.
EOF
}

nodes=()
environment="intern"
policy_prefix="lx-hub-site"
pki_mount="lx-hub-pki"
secrets_mount="lx-hub-secrets"
out_dir=""
dry_run=false

append_node() {
  local raw_node="$1"
  local node="${raw_node%"${raw_node##*[![:space:]]}"}"
  node="${node#"${node%%[![:space:]]*}"}"
  if [[ -z "$node" ]]; then
    return
  fi
  if [[ ! "$node" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: invalid node '$node'. Allowed chars: A-Z a-z 0-9 . _ -" >&2
    exit 2
  fi
  nodes+=("$node")
}

append_nodes_from_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "ERROR: nodes file not found: $path" >&2
    exit 2
  fi
  local in_nodes_section=0
  local in_policy_section=0
  while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
    raw_line="${raw_line%%#*}"
    if [[ -z "${raw_line//[[:space:]]/}" ]]; then
      continue
    fi

    if [[ "$raw_line" =~ ^[[:space:]]*nodes:[[:space:]]*$ ]]; then
      in_nodes_section=1
      in_policy_section=0
      continue
    fi
    if [[ "$raw_line" =~ ^[[:space:]]*policy:[[:space:]]*$ ]]; then
      in_nodes_section=0
      in_policy_section=1
      continue
    fi
    if [[ "$raw_line" == *":"* && ! "$raw_line" =~ ^[[:space:]]*- ]]; then
      in_nodes_section=0
      in_policy_section=0
    fi

    if (( in_nodes_section == 1 )); then
      if [[ "$raw_line" =~ ^[[:space:]]*-[[:space:]]*(.+)$ ]]; then
        append_node "${BASH_REMATCH[1]}"
      fi
      continue
    fi

    if (( in_policy_section == 1 )); then
      if [[ "$raw_line" =~ ^[[:space:]]*environment:[[:space:]]*(.+)$ ]]; then
        [[ -n "${BASH_REMATCH[1]}" ]] && environment="${BASH_REMATCH[1]}"
      elif [[ "$raw_line" =~ ^[[:space:]]*prefix:[[:space:]]*(.+)$ ]]; then
        [[ -n "${BASH_REMATCH[1]}" ]] && policy_prefix="${BASH_REMATCH[1]}"
      elif [[ "$raw_line" =~ ^[[:space:]]*pki_mount:[[:space:]]*(.+)$ ]]; then
        [[ -n "${BASH_REMATCH[1]}" ]] && pki_mount="${BASH_REMATCH[1]}"
      elif [[ "$raw_line" =~ ^[[:space:]]*secrets_mount:[[:space:]]*(.+)$ ]]; then
        [[ -n "${BASH_REMATCH[1]}" ]] && secrets_mount="${BASH_REMATCH[1]}"
      fi
    fi
  done < "$path"
}

while (( $# )); do
  case "$1" in
    --node)
      append_node "${2:?node value required}"
      shift 2
      ;;
    --nodes-file)
      append_nodes_from_file "${2:?nodes file path required}"
      shift 2
      ;;
    --environment)
      environment="${2:?environment value required}"
      shift 2
      ;;
    --policy-prefix)
      policy_prefix="${2:?policy prefix required}"
      shift 2
      ;;
    --pki-mount)
      pki_mount="${2:?pki mount required}"
      shift 2
      ;;
    --secrets-mount)
      secrets_mount="${2:?secrets mount required}"
      shift 2
      ;;
    --out-dir)
      out_dir="${2:?output directory required}"
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ((${#nodes[@]} == 0)); then
  echo "ERROR: provide at least one --node or --nodes-file." >&2
  usage >&2
  exit 2
fi

if ! command -v vault >/dev/null 2>&1; then
  echo "ERROR: vault binary not found in PATH." >&2
  exit 2
fi

if [[ -n "$out_dir" ]]; then
  mkdir -p "$out_dir"
fi

policy_count=0
for node in "${nodes[@]}"; do
  issue_node="${node}_${environment}"
  secret_node="${node//_/-}"
  policy_name="${policy_prefix}-${issue_node}"

  policy_file="$(mktemp)"
  cat <<EOF > "$policy_file"
path "${pki_mount}/issue/site-${issue_node}" {
  capabilities = ["create", "update"]
}

path "${pki_mount}/cert/ca" {
  capabilities = ["read"]
}

path "${secrets_mount}/data/nodes/${secret_node}.${environment}" {
  capabilities = ["read"]
}

path "${secrets_mount}/data/hub/envelope-recipient/current" {
  capabilities = ["read"]
}
EOF

  if [[ -n "$out_dir" ]]; then
    cp "$policy_file" "$out_dir/${policy_name}.hcl"
  fi

  if [[ "$dry_run" == true ]]; then
    echo "DRY-RUN: ${policy_name}"
    cat "$policy_file"
    echo
  else
    echo "Writing policy ${policy_name}"
    vault policy write "$policy_name" "$policy_file"
  fi

  rm -f "$policy_file"
  ((policy_count++))
done

if [[ "$dry_run" == true ]]; then
  echo "DRY-RUN complete: ${policy_count} policies generated."
else
  echo "Done: ${policy_count} policies written to Vault."
fi
