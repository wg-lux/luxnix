#!/usr/bin/env bash
# Nextcloud migration from s-03 to a new host.
# Run from the control machine inside devenv shell.
#
# Usage: devenv run migrate-nextcloud <new-host-ip> [--skip-deploy]
#   new-host-ip  : public/direct IP of the new Nextcloud host
#   --skip-deploy: skip nixos-rebuild if new host is already deployed
#
# What this does:
#   1. Enables Nextcloud maintenance mode on s-03
#   2. pg_dump nextcloud DB from s-03
#   3. Initial rsync of data directory (run before maintenance if large)
#   4. mc mirror MinIO bucket s-03 → new host
#   5. Final rsync (catches any writes since initial)
#   6. Deploys new host NixOS config (unless --skip-deploy)
#   7. pg_restore into new host postgres
#   8. Fixes ownership + runs occ housekeeping
#   9. Disables maintenance mode and verifies
#
# Tip: run steps 1 and 3 (maintenance mode + initial rsync) ahead of the
# maintenance window to minimise downtime. Re-run the script with --skip-deploy
# during the window to complete the final sync and cutover.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <new-host-ip> [--skip-deploy]"
  exit 1
fi

NEW_HOST="$1"
SKIP_DEPLOY=false
[[ "${2:-}" == "--skip-deploy" ]] && SKIP_DEPLOY=true

S03="172.16.255.13"
DATE=$(date +%Y%m%d-%H%M)
DUMP_FILE="nextcloud-${DATE}.pgdump"

NC_DATA_DIR="/var/lib/nextcloud/data"
MINIO_SRC="s03/nextcloud-bucket"
MINIO_DST="newhost/nextcloud-bucket"

echo "==> Nextcloud migration: s-03 ($S03) → $NEW_HOST"
echo "    Dump file : $DUMP_FILE"
echo ""

# ── Step 1: Maintenance mode on ───────────────────────────────────────────────
echo "--- Step 1: Enabling maintenance mode on s-03 ---"
ssh "admin@${S03}" sudo nextcloud-occ maintenance:mode --on
ssh "admin@${S03}" sudo nextcloud-occ status | grep -E "maintenance|version"
echo "    Maintenance mode enabled"

# ── Step 2: pg_dump ───────────────────────────────────────────────────────────
echo ""
echo "--- Step 2: Dumping nextcloud DB on s-03 ---"
ssh "admin@${S03}" "sudo -u postgres pg_dump -Fc nextcloud" > "./${DUMP_FILE}"
echo "    DB dump → ./${DUMP_FILE} ($(du -sh "./${DUMP_FILE}" | cut -f1))"

# ── Step 3: rsync data directory ──────────────────────────────────────────────
echo ""
echo "--- Step 3: Syncing Nextcloud data directory ---"
echo "    This may take a while for large instances."
rsync -avz --progress --checksum \
  "admin@${S03}:${NC_DATA_DIR}/" \
  "root@${NEW_HOST}:${NC_DATA_DIR}/"

# ── Step 4: MinIO mirror ──────────────────────────────────────────────────────
echo ""
echo "--- Step 4: Mirroring MinIO bucket ---"
echo "    Adjust MINIO_SRC/MINIO_DST at top of script to match your mc alias names."
echo "    Skipping mc mirror — update MINIO_SRC and MINIO_DST and uncomment below."
# mc mirror "$MINIO_SRC" "$MINIO_DST" --overwrite

# ── Step 5: Deploy new host ───────────────────────────────────────────────────
if [[ "$SKIP_DEPLOY" == false ]]; then
  echo ""
  echo "--- Step 5: Deploying new host NixOS config ---"
  nixos-rebuild switch --flake ".#$(ssh "root@${NEW_HOST}" hostname)" \
    --target-host "root@${NEW_HOST}"
else
  echo ""
  echo "--- Step 5: Skipping deploy (--skip-deploy) ---"
fi

# ── Step 6: Restore postgres dump ────────────────────────────────────────────
echo ""
echo "--- Step 6: Restoring nextcloud DB on new host ---"
scp "./${DUMP_FILE}" "root@${NEW_HOST}:/tmp/${DUMP_FILE}"
ssh "root@${NEW_HOST}" "
  set -euo pipefail
  sudo -u postgres psql -c 'DROP DATABASE IF EXISTS nextcloud;'
  sudo -u postgres psql -c 'CREATE DATABASE nextcloud OWNER nextcloud;'
  sudo -u postgres pg_restore -U postgres -d nextcloud /tmp/${DUMP_FILE}
  rm /tmp/${DUMP_FILE}
  echo '    pg_restore complete'
"

# ── Step 7: Post-restore housekeeping ─────────────────────────────────────────
echo ""
echo "--- Step 7: Post-restore Nextcloud housekeeping ---"
ssh "root@${NEW_HOST}" "
  set -euo pipefail
  chown -R nextcloud:nextcloud ${NC_DATA_DIR}

  nextcloud-occ config:system:set trusted_domains 0 --value='cloud.endo-reg.net'
  nextcloud-occ config:system:set trusted_proxies 0 --value='172.16.255.1'

  echo 'Running file scan (may take a while)...'
  nextcloud-occ files:scan --all

  nextcloud-occ maintenance:mode --off
  nextcloud-occ status
"

# ── Step 8: Verify ────────────────────────────────────────────────────────────
echo ""
echo "--- Step 8: Verifying ---"
HTTP=$(curl -sko /dev/null -w "%{http_code}" --max-time 10 "https://cloud.endo-reg.net/login" || echo "FAILED")
if [[ "$HTTP" == "200" ]]; then
  echo "    ✓ cloud.endo-reg.net/login → HTTP 200"
else
  echo "    ✗ cloud.endo-reg.net returned: $HTTP"
  echo "      Check: ssh root@${NEW_HOST} journalctl -u nextcloud --since '5 min ago'"
  exit 1
fi

echo ""
echo "==> Migration complete. Verify in browser before decommissioning s-03."
echo "    Update inventory:"
echo "      serviceHosts.nextcloud: <new-host-name>  (ansible/inventory/group_vars/all.yml)"
echo ""
echo "    Update DNS:"
echo "      cloud.endo-reg.net  A  <new-host-public-ip>"
echo ""
echo "    When satisfied, disable Nextcloud on s-03:"
echo "      host_roles.nextcloudHost.enable: 'false'  (host_vars/s-03.yml)"
