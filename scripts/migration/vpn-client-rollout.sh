#!/usr/bin/env bash
# Roll gc-* GPU clients over from s-01 VPN to h-01 VPN, one at a time.
#
# Prerequisites:
#   1. h-01 VPN server is running
#   2. vpn.endo-reg.net DNS has been updated to point to h-01 (178.104.136.182)
#   3. gc-* machines are still connected to s-01 (existing TCP sessions survive DNS change)
#   4. Control machine has SSH access to both h-01 (public IP) and gc-* (via VPN)
#
# Usage: devenv run vpn-client-rollout
#
# All servers (s-*, gs-*) have direct SSH access and are not VPN-dependent.
# Only gc-* machines are VPN-only — this script handles them.
set -euo pipefail

H01="178.104.136.182"

# Active gc-* hosts and their fixed VPN IPs (from CCD)
declare -A GC_HOSTS=(
  ["gc-02"]="172.16.255.102"
  ["gc-04"]="172.16.255.104"
  ["gc-05"]="172.16.255.105"
  ["gc-06"]="172.16.255.106"
  ["gc-07"]="172.16.255.107"
  ["gc-08"]="172.16.255.108"
  ["gc-09"]="172.16.255.109"
  ["gc-10"]="172.16.255.110"
)

PASS=0
FAIL=0
SKIP=0

check_connected_to_h01() {
  local ip="$1"
  # Check h-01 openvpn log for recent connection from this IP
  ssh -o ConnectTimeout=5 "root@${H01}" \
    "journalctl -u openvpn-aglnet --since '60 seconds ago' 2>/dev/null | grep -q '${ip}'" 2>/dev/null
}

echo "==> Pre-flight: verifying h-01 VPN server is active..."
if ! ssh -o ConnectTimeout=5 "root@${H01}" systemctl is-active --quiet openvpn-aglnet.service; then
  echo "ERROR: h-01 openvpn-aglnet.service is not running. Aborting."
  exit 1
fi
echo "    OK"

echo ""
echo "==> Rolling over ${#GC_HOSTS[@]} gc-* clients to h-01..."
echo "    Each machine is restarted one at a time via its current s-01 VPN session."
echo ""

for host in $(echo "${!GC_HOSTS[@]}" | tr ' ' '\n' | sort); do
  ip="${GC_HOSTS[$host]}"
  echo "--- $host ($ip) ---"

  # Attempt restart via current VPN session (s-01 or h-01 — whichever is active)
  if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "admin@${ip}" \
      sudo systemctl restart openvpn-aglnet.service 2>/dev/null; then
    echo "  SKIP: could not reach $host at $ip — already unreachable or not active"
    (( SKIP++ )) || true
    echo ""
    continue
  fi

  echo "  Restarted openvpn-aglnet — waiting for reconnect to h-01..."
  sleep 10

  if check_connected_to_h01 "$ip"; then
    echo "  ✓ $host reconnected to h-01"
    (( PASS++ )) || true
  else
    echo "  ? $host: not yet visible in h-01 logs — verify manually:"
    echo "      ssh root@${H01} journalctl -u openvpn-aglnet --since '2 min ago' | grep ${ip}"
    (( FAIL++ )) || true
  fi
  echo ""
done

echo "=== Summary ==="
echo "  Reconnected to h-01 : $PASS"
echo "  Not confirmed        : $FAIL"
echo "  Skipped (unreachable): $SKIP"
echo ""

if [[ $PASS -eq ${#GC_HOSTS[@]} ]]; then
  echo "All gc-* clients confirmed on h-01."
  echo "You can now stop the s-01 VPN server:"
  echo "  ssh admin@172.16.255.1 sudo systemctl stop openvpn-aglnet.service"
else
  echo "Some clients not confirmed. Check manually before stopping s-01 VPN server."
  echo "Active connections on h-01:"
  ssh -o ConnectTimeout=5 "root@${H01}" \
    "journalctl -u openvpn-aglnet --since '10 min ago' | grep 'peer connection\|MULTI_sva'" 2>/dev/null || true
fi
