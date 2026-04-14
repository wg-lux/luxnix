#!/usr/bin/env bash
# Full Keycloak + postgres data migration from s-02 to h-01.
# Run from the control machine inside devenv shell.
#
# Usage: devenv run migrate-keycloak [--skip-deploy]
#   --skip-deploy: skip nixos-rebuild if h-01 is already deployed
#
# What this does:
#   1. Stops Keycloak on s-02
#   2. Exports realm JSON (fallback/verification copy)
#   3. pg_dump keycloak DB from s-02
#   4. Deploys h-01 NixOS config (unless --skip-deploy)
#   5. Stops Keycloak on h-01 before it can touch the empty DB
#   6. pg_restore dump into h-01 postgres
#   7. Aligns DB user password via keycloak-db-setup.service
#   8. Starts Keycloak on h-01 and verifies realm is accessible
set -euo pipefail

SKIP_DEPLOY=false
[[ "${1:-}" == "--skip-deploy" ]] && SKIP_DEPLOY=true

S02="172.16.255.12"
H01="178.104.136.182"
DATE=$(date +%Y%m%d-%H%M)
DUMP_FILE="keycloak-${DATE}.pgdump"
EXPORT_DIR="keycloak-export-${DATE}"

echo "==> Keycloak migration: s-02 → h-01"
echo "    Dump file : $DUMP_FILE"
echo "    Export dir: $EXPORT_DIR"
echo ""

# ── Step 1: Stop Keycloak on s-02 ────────────────────────────────────────────
echo "--- Step 1: Stopping Keycloak on s-02 ---"
ssh "admin@${S02}" sudo systemctl stop keycloak.service
echo "    Done"

# ── Step 2: Export realm JSON ─────────────────────────────────────────────────
echo ""
echo "--- Step 2: Exporting Keycloak realms from s-02 ---"
ssh "admin@${S02}" "
  sudo rm -rf /tmp/keycloak-export
  sudo -u keycloak mkdir -p /tmp/keycloak-export
  sudo -u keycloak /run/current-system/sw/bin/kc.sh export \
    --dir /tmp/keycloak-export \
    --users realm_file 2>&1
"
scp -r "admin@${S02}:/tmp/keycloak-export" "./${EXPORT_DIR}"
echo "    Realm export → ./${EXPORT_DIR}"

# ── Step 3: pg_dump ───────────────────────────────────────────────────────────
echo ""
echo "--- Step 3: Dumping keycloak DB on s-02 ---"
ssh "admin@${S02}" "sudo -u postgres pg_dump -Fc keycloak" > "./${DUMP_FILE}"
echo "    DB dump → ./${DUMP_FILE} ($(du -sh "./${DUMP_FILE}" | cut -f1))"

# ── Step 4: Deploy h-01 ───────────────────────────────────────────────────────
if [[ "$SKIP_DEPLOY" == false ]]; then
  echo ""
  echo "--- Step 4: Deploying h-01 NixOS config ---"
  nixos-rebuild switch --flake ".#h-01" --target-host "root@${H01}"
else
  echo ""
  echo "--- Step 4: Skipping deploy (--skip-deploy) ---"
fi

# ── Step 5: Stop Keycloak on h-01 before it initialises the empty DB ─────────
echo ""
echo "--- Step 5: Stopping Keycloak on h-01 before restore ---"
ssh "root@${H01}" "systemctl stop keycloak.service keycloak-db-setup.service 2>/dev/null || true"
echo "    Done"

# ── Step 6: Restore postgres dump ────────────────────────────────────────────
echo ""
echo "--- Step 6: Restoring postgres dump on h-01 ---"
scp "./${DUMP_FILE}" "root@${H01}:/tmp/${DUMP_FILE}"
ssh "root@${H01}" "
  set -euo pipefail
  sudo -u postgres psql -c 'DROP DATABASE IF EXISTS keycloak;'
  sudo -u postgres psql -c 'CREATE DATABASE keycloak OWNER keycloak;'
  sudo -u postgres pg_restore -U postgres -d keycloak /tmp/${DUMP_FILE}
  rm /tmp/${DUMP_FILE}
  echo '    pg_restore complete'
"

# ── Step 7: Align DB user password ───────────────────────────────────────────
echo ""
echo "--- Step 7: Aligning DB password via keycloak-db-setup ---"
ssh "root@${H01}" systemctl start keycloak-db-setup.service
# Wait for the oneshot to finish (max 60s)
for i in $(seq 1 12); do
  sleep 5
  STATUS=$(ssh "root@${H01}" systemctl is-active keycloak-db-setup.service 2>/dev/null || echo "unknown")
  if [[ "$STATUS" == "inactive" ]]; then
    echo "    keycloak-db-setup finished"
    break
  fi
  echo "    Waiting... ($((i*5))s)"
done
ssh "root@${H01}" "journalctl -u keycloak-db-setup --since '2 min ago' | tail -5"

# ── Step 8: Start Keycloak and verify ─────────────────────────────────────────
echo ""
echo "--- Step 8: Starting Keycloak on h-01 ---"
ssh "root@${H01}" systemctl start keycloak.service
echo "    Waiting 40s for startup..."
sleep 40

echo ""
echo "--- Step 9: Verifying ---"
REALM=$(curl -sk --max-time 10 "https://keycloak.endo-reg.net/realms/master" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('realm','MISSING'))" \
  2>/dev/null || echo "CURL_FAILED")

if [[ "$REALM" == "master" ]]; then
  echo "    ✓ realm 'master' accessible — Keycloak is healthy"
else
  echo "    ✗ Realm check returned: $REALM"
  echo ""
  echo "    Check logs on h-01:"
  echo "      ssh root@${H01} journalctl -u keycloak --since '5 min ago'"
  echo ""
  echo "    Fallback: import realm JSON if pg_restore had errors:"
  echo "      scp -r ./${EXPORT_DIR} root@${H01}:/tmp/keycloak-export"
  echo "      ssh root@${H01} sudo -u keycloak /run/current-system/sw/bin/kc.sh import \\"
  echo "        --dir /tmp/keycloak-export --override true"
  exit 1
fi

echo ""
echo "==> Migration complete."
echo "    Update DNS when ready:"
echo "      keycloak.endo-reg.net       A  ${H01}"
echo "      adminKeycloak.endo-reg.net  A  ${H01}"
echo ""
echo "    Rollback: revert DNS + ssh admin@${S02} sudo systemctl start keycloak.service"
