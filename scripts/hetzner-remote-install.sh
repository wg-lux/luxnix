#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

HOST_PROFILE="${HOST_PROFILE:-h-01}"
TARGET_HOST="${TARGET_HOST:-root@178.104.136.182}"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/ssh-hetzner-main_openssh}"
REFRESH_HOST_KEY="${REFRESH_HOST_KEY:-false}"

usage() {
	cat <<'EOF'
Usage:
	./scripts/hetzner-remote-install.sh [options] [target-host] [key-file]

Options:
	--refresh-host-key  Remove stale known_hosts entries for target before install.
	-h, --help          Show this help text.

Arguments:
	target-host   Optional. SSH target in user@host format.
	key-file      Optional. Path to SSH private key.

Environment overrides:
	HOST_PROFILE     NixOS host profile in flake (default: h-01)
	TARGET_HOST      SSH target (default: root@178.104.136.182)
	KEY_FILE         SSH key file (default: ~/.ssh/ssh-hetzner-main_openssh)
	REFRESH_HOST_KEY true|false (default: false)

Examples:
	./scripts/hetzner-remote-install.sh
	./scripts/hetzner-remote-install.sh --refresh-host-key
	./scripts/hetzner-remote-install.sh root@178.104.136.182 ~/.ssh/ssh-hetzner-main_openssh --refresh-host-key
	REFRESH_HOST_KEY=true ./scripts/hetzner-remote-install.sh
	HOST_PROFILE=h-01 TARGET_HOST=root@1.2.3.4 KEY_FILE=~/.ssh/ssh-hetzner-main_openssh REFRESH_HOST_KEY=true ./scripts/hetzner-remote-install.sh
EOF
}

positionals=()
while [[ $# -gt 0 ]]; do
	case "$1" in
		-h|--help)
			usage
			exit 0
			;;
		--refresh-host-key)
			REFRESH_HOST_KEY="true"
			;;
		--)
			shift
			while [[ $# -gt 0 ]]; do
				positionals+=("$1")
				shift
			done
			break
			;;
		-*)
			echo "Error: unknown option: $1" >&2
			usage
			exit 1
			;;
		*)
			positionals+=("$1")
			;;
	esac
	shift
done

if [[ ${#positionals[@]} -ge 1 ]]; then
	TARGET_HOST="${positionals[0]}"
fi

if [[ ${#positionals[@]} -ge 2 ]]; then
	KEY_FILE="${positionals[1]}"
fi

if [[ ! -f "$KEY_FILE" ]]; then
	echo "Error: key file not found: $KEY_FILE" >&2
	exit 1
fi

if [[ ! -r "$KEY_FILE" ]]; then
	echo "Error: key file is not readable: $KEY_FILE" >&2
	exit 1
fi

extract_ssh_host() {
	local target="$1"
	local hostpart

	hostpart="${target##*@}"

	if [[ "$hostpart" == \[*\] ]]; then
		hostpart="${hostpart#\[}"
		hostpart="${hostpart%\]}"
		printf '%s\n' "$hostpart"
		return 0
	fi

	if [[ "$hostpart" == \[*\]:* ]]; then
		hostpart="${hostpart#\[}"
		hostpart="${hostpart%%\]:*}"
		printf '%s\n' "$hostpart"
		return 0
	fi

	if [[ "$hostpart" == *:* ]] && [[ "$hostpart" != *:*:* ]]; then
		hostpart="${hostpart%%:*}"
	fi

	printf '%s\n' "$hostpart"
}

if [[ "$REFRESH_HOST_KEY" == "true" ]]; then
	ssh_host="$(extract_ssh_host "$TARGET_HOST")"
	echo "Refreshing known_hosts entries for ${ssh_host}"
	ssh-keygen -R "$ssh_host" >/dev/null 2>&1 || true
	ssh-keygen -R "[${ssh_host}]:22" >/dev/null 2>&1 || true
fi

echo "Installing profile .#${HOST_PROFILE} to ${TARGET_HOST} using key ${KEY_FILE}"

cd "$REPO_ROOT"

nix run --extra-experimental-features 'nix-command flakes' github:nix-community/nixos-anywhere -- \
	--flake ".#${HOST_PROFILE}" \
	--option require-sigs false \
	--ssh-store-setting trusted true \
	--build-on local \
	--target-host "$TARGET_HOST" \
	--ssh-option "IdentityFile=$KEY_FILE" \
	--ssh-option "IdentitiesOnly=yes" \
	--ssh-option "StrictHostKeyChecking=accept-new"
