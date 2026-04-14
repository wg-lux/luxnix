#!/usr/bin/env bash
# Full Keycloak + postgres data migration from s-02 to h-01.
# Run from the control machine inside devenv shell.
#
# Usage: migrate-keycloak [--skip-deploy]
#   --skip-deploy: skip nixos-rebuild if h-01 is already deployed
#
# What this does:
#   1. Stops Keycloak on s-02
#   2. Exports realm JSON (fallback/verification copy — best-effort)
#   3. pg_dump keycloak DB from s-02
#   4. Deploys h-01 NixOS config (unless --skip-deploy)
#   5. Stops Keycloak on h-01 before it can touch the empty DB
#   6. pg_restore dump into h-01 postgres
#   7. Aligns DB user password via keycloak-db-setup.service
#   8. Starts Keycloak on h-01 and verifies realm is accessible
#
# SSH notes:
#   s-02: accessed as admin@s-02 (requires sudo password — wheelNeedsPassword=true)
#   h-01: accessed as admin@h-01 (root SSH not configured; sudo -S used throughout)
#         Step 4 (nixos-rebuild --target-host) is skipped with --skip-deploy since
#         it requires root SSH access; use ansible or nixos-anywhere for deploys.
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

# ── Credentials ──────────────────────────────────────────────────────────────
# s-02: base-server role → wheelNeedsPassword=true, needs sudo password.
#   Steps 1-2 use ssh -t (interactive TTY) so sudo can prompt.
#   Step 3 pipes via stdin to avoid -t corrupting binary pg_dump output.
# h-01: hetzner role (wheelNeedsPassword not yet deployed) → needs sudo password.
#   All h-01 steps use sudo -S with the password piped via stdin.
#   NixOS does not set Defaults requiretty so sudo -S works without a TTY.
read -rsp "s-02 admin sudo password: " S02_PASS
echo ""
read -rsp "h-01 admin sudo password: " H01_PASS
echo ""

# ── Step 1: Stop Keycloak on s-02 ────────────────────────────────────────────
echo "--- Step 1: Stopping Keycloak on s-02 ---"
ssh -t "admin@${S02}" "sudo systemctl stop keycloak.service"
echo "    Done"

# ── Step 2: Export realm JSON ─────────────────────────────────────────────────
# Fallback/verification copy only — pg_dump (step 3) is the primary source.
# kc.sh export --optimized must run from /var/lib/keycloak (service WorkingDirectory)
# so Keycloak can find its Quarkus build artifacts.  Soft-fail: a broken export
# does not block the migration.
echo ""
echo "--- Step 2: Exporting Keycloak realms from s-02 (best-effort) ---"
if ssh -t "admin@${S02}" "
  sudo rm -rf /tmp/keycloak-export
  sudo -u keycloak mkdir -p /tmp/keycloak-export
  sudo -u keycloak sh -c 'cd /var/lib/keycloak && /run/current-system/sw/bin/kc.sh export \
    --optimized \
    --dir /tmp/keycloak-export \
    --users realm_file 2>&1'
"; then
  scp -r "admin@${S02}:/tmp/keycloak-export" "./${EXPORT_DIR}"
  echo "    Realm export → ./${EXPORT_DIR}"
else
  echo "    ⚠  Realm JSON export failed — continuing without it."
  echo "    pg_dump (step 3) is the authoritative migration source; the JSON is only a fallback."
fi

# ── Step 3: pg_dump ───────────────────────────────────────────────────────────
# Cannot use ssh -t here: a pseudo-TTY would inject terminal control bytes into
# the binary pg_dump stream and corrupt the file.  Pipe the password to sudo -S
# via SSH stdin instead.
echo ""
echo "--- Step 3: Dumping keycloak DB on s-02 ---"
printf '%s\n' "${S02_PASS}" | ssh "admin@${S02}" "sudo -S -u postgres pg_dump -Fc keycloak" > "./${DUMP_FILE}"
echo "    DB dump → ./${DUMP_FILE} ($(du -sh "./${DUMP_FILE}" | cut -f1))"

# ── Step 4: Deploy h-01 ───────────────────────────────────────────────────────
# NOTE: nixos-rebuild --target-host requires root SSH which is not configured on
# h-01.  Use ansible (ansible-playbook site.yml --limit h-01) or nixos-anywhere
# for deploys, then re-run with --skip-deploy.
if [[ "$SKIP_DEPLOY" == false ]]; then
  echo ""
  echo "--- Step 4: Deploying h-01 NixOS config ---"
  echo "    WARNING: this requires root SSH access to h-01 which may not be configured."
  nixos-rebuild switch --flake ".#h-01" --target-host "root@${H01}"
else
  echo ""
  echo "--- Step 4: Skipping deploy (--skip-deploy) ---"
fi

# ── Step 5: Stop Keycloak on h-01 before it initialises the empty DB ─────────
echo ""
echo "--- Step 5: Stopping Keycloak on h-01 before restore ---"
printf '%s\n' "${H01_PASS}" | ssh "admin@${H01}" \
  "sudo -S bash -c 'systemctl stop keycloak.service keycloak-db-setup.service 2>/dev/null; true'"
echo "    Done"

# ── Step 6: Restore postgres dump ────────────────────────────────────────────
echo ""
echo "--- Step 6: Restoring postgres dump on h-01 ---"
scp "./${DUMP_FILE}" "admin@${H01}:/tmp/${DUMP_FILE}"
# Pipe password then the restore script into sudo -S bash -s.
# sudo reads the first line as the password; bash -s reads the rest as the script.
# runuser is used instead of nested sudo: as root, runuser switches to postgres
# without needing a password.
{ printf '%s\n' "${H01_PASS}"; cat <<EOF
set -euo pipefail
runuser -u postgres -- psql -c 'DROP DATABASE IF EXISTS keycloak;'
runuser -u postgres -- psql -c 'CREATE DATABASE keycloak OWNER keycloak;'
runuser -u postgres -- pg_restore -d keycloak /tmp/${DUMP_FILE}
rm /tmp/${DUMP_FILE}
echo '    pg_restore complete'
EOF
} | ssh "admin@${H01}" "sudo -S bash -s"

# ── Step 7: Align DB user password ───────────────────────────────────────────
echo ""
echo "--- Step 7: Aligning DB password via keycloak-db-setup ---"
printf '%s\n' "${H01_PASS}" | ssh "admin@${H01}" "sudo -S systemctl start keycloak-db-setup.service"
# Wait for the oneshot to finish (max 60s)
for i in $(seq 1 12); do
  sleep 5
  STATUS=$(ssh "admin@${H01}" "systemctl is-active keycloak-db-setup.service" 2>/dev/null || echo "unknown")
  if [[ "$STATUS" == "inactive" ]]; then
    echo "    keycloak-db-setup finished"
    break
  fi
  echo "    Waiting... ($((i*5))s)"
done
printf '%s\n' "${H01_PASS}" | ssh "admin@${H01}" \
  "sudo -S journalctl -u keycloak-db-setup --since '2 min ago' | tail -5"

# ── Step 8: Start Keycloak and verify ─────────────────────────────────────────
echo ""
echo "--- Step 8: Starting Keycloak on h-01 ---"
printf '%s\n' "${H01_PASS}" | ssh "admin@${H01}" "sudo -S systemctl start keycloak.service"
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
  echo "      ssh admin@${H01} sudo journalctl -u keycloak --since '5 min ago'"
  echo ""
  echo "    Fallback: import realm JSON if pg_restore had errors:"
  echo "      scp -r ./${EXPORT_DIR} admin@${H01}:/tmp/keycloak-export"
  echo "      ssh admin@${H01} sudo -u keycloak /run/current-system/sw/bin/kc.sh import \\"
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
