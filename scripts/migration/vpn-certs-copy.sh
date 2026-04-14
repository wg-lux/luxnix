#!/usr/bin/env bash
# Copy VPN cert material from s-01 to h-01.
# Run from the control machine — both hosts must be SSH-reachable.
#
# Usage: devenv run migrate-vpn-certs [s01-host] [h01-host]
#   s01-host defaults to 172.16.255.1  (s-01 VPN IP or direct if reachable)
#   h01-host defaults to 178.104.136.182  (h-01 public IP)
set -euo pipefail

S01="${1:-172.16.255.1}"
H01="${2:-178.104.136.182}"

CERTS=(ca.pem crt.crt key.key dh.pem tls.pem)

echo "==> Copying VPN cert material: s-01 ($S01) → h-01 ($H01)"

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "--- Fetching certs from s-01 ---"
for f in "${CERTS[@]}"; do
  echo "  $f"
  scp "admin@${S01}:/etc/openvpn/$f" "$TMPDIR/$f"
done
scp -r "admin@${S01}:/etc/openvpn/ccd" "$TMPDIR/ccd"

echo ""
echo "--- Deploying to h-01 ---"
for f in "${CERTS[@]}"; do
  echo "  $f"
  scp "$TMPDIR/$f" "root@${H01}:/tmp/ovpn-$f"
  ssh "root@${H01}" "install -m 600 -o root -g root /tmp/ovpn-$f /etc/openvpn/$f && rm /tmp/ovpn-$f"
done

scp -r "$TMPDIR/ccd" "root@${H01}:/tmp/ovpn-ccd"
ssh "root@${H01}" "
  cp -r /tmp/ovpn-ccd /etc/openvpn/ccd
  chmod 755 /etc/openvpn/ccd
  chmod 644 /etc/openvpn/ccd/*
  rm -rf /tmp/ovpn-ccd
"

echo ""
echo "--- Verification on h-01 ---"
ssh "root@${H01}" "ls -la /etc/openvpn/ && echo '' && ls /etc/openvpn/ccd/"

echo ""
echo "==> Done. Run 'devenv run vpn-client-rollout' after DNS cutover."
