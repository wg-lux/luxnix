{
  config,
  lib,
  pkgs,
  cfg,
  ...
}:
{
  runLocalHubBackupScript = pkgs.writeShellScriptBin "runLxAnnotateHubBackup" ''
        set -euo pipefail

        runtime_root="${cfg.hub.backup.sourceRuntimeDir}"
        incoming_root="${cfg.hub.backup.incomingDir}"
        snapshot_root="${cfg.hub.backup.snapshotDir}"
        manifest_root="${cfg.hub.backup.manifestDir}"
        latest_link="$snapshot_root/latest"
        retain_count="${toString cfg.hub.backup.retainCount}"
        host_name="${config.networking.hostName}"
        timestamp="$(${pkgs.coreutils}/bin/date -u +%Y%m%dT%H%M%S%NZ)"
        pending_snapshot="$snapshot_root/.pending-$timestamp"
        completed_snapshot="$snapshot_root/$timestamp"
        manifest_file="$manifest_root/$timestamp.json"
        checksum_file="$manifest_root/$timestamp.sha256"
        pending_manifest="$manifest_root/.pending-$timestamp.json"
        pending_checksums="$manifest_root/.pending-$timestamp.sha256"
        pending_latest="$snapshot_root/.latest-$timestamp"
        previous_snapshot=""

        if [ ! -d "$runtime_root" ]; then
          echo "ERROR: hub backup runtime root is missing: $runtime_root" >&2
          exit 1
        fi

        install -d -m 0750 "$incoming_root" "$snapshot_root" "$manifest_root"
        cleanup_pending() {
          rm -rf "$pending_snapshot"
          rm -f "$pending_manifest" "$pending_checksums" "$pending_latest"
        }
        trap cleanup_pending EXIT
        cleanup_pending
        install -d -m 0750 "$pending_snapshot"

        if [ -L "$latest_link" ]; then
          previous_snapshot="$(${pkgs.coreutils}/bin/readlink -f "$latest_link" 2>/dev/null || true)"
        fi

        rsync_cmd=(
          ${pkgs.rsync}/bin/rsync
          -a
          --delete
          --numeric-ids
          --chmod=F640,D750
        )

        if [ -n "$previous_snapshot" ] && [ -d "$previous_snapshot" ]; then
          rsync_cmd+=(--link-dest "$previous_snapshot")
        fi

        ${lib.concatStringsSep "\n" (map (pattern: "rsync_cmd+=(--exclude ${lib.escapeShellArg pattern})") cfg.hub.backup.exclude)}

        rsync_cmd+=("$runtime_root/" "$pending_snapshot/")
        "''${rsync_cmd[@]}"

        (
          cd "$pending_snapshot"
          LC_ALL=C ${pkgs.findutils}/bin/find . -type f -print0 \
            | ${pkgs.coreutils}/bin/sort -z \
            | ${pkgs.findutils}/bin/xargs -0 -r ${pkgs.coreutils}/bin/sha256sum
        ) > "$pending_checksums"
        (
          cd "$pending_snapshot"
          ${pkgs.coreutils}/bin/sha256sum --check "$pending_checksums"
        )

        file_count="$(${pkgs.findutils}/bin/find "$pending_snapshot" -type f | ${pkgs.coreutils}/bin/wc -l | ${pkgs.gawk}/bin/awk '{print $1}')"
        size_bytes="$(${pkgs.findutils}/bin/find "$pending_snapshot" -type f -printf '%s\n' | ${pkgs.gawk}/bin/awk '{sum += $1} END {print sum + 0}')"
        checksum_sha256="$(${pkgs.coreutils}/bin/sha256sum "$pending_checksums" | ${pkgs.gawk}/bin/awk '{print $1}')"

        ${pkgs.jq}/bin/jq -n \
          --arg generated_at "$(${pkgs.coreutils}/bin/date -u --iso-8601=seconds)" \
          --arg hostname "$host_name" \
          --arg runtime_root "$runtime_root" \
          --arg incoming_root "$incoming_root" \
          --arg snapshot_dir "$completed_snapshot" \
          --arg checksum_file "$checksum_file" \
          --arg checksum_sha256 "$checksum_sha256" \
          --argjson retain_count "$retain_count" \
          --argjson file_count "$file_count" \
          --argjson size_bytes "$size_bytes" \
          --argjson exclude '${builtins.toJSON cfg.hub.backup.exclude}' \
          '{
            generated_at: $generated_at,
            hostname: $hostname,
            runtime_root: $runtime_root,
            incoming_root: $incoming_root,
            snapshot_dir: $snapshot_dir,
            checksum_file: $checksum_file,
            checksum_sha256: $checksum_sha256,
            retain_count: $retain_count,
            file_count: $file_count,
            size_bytes: $size_bytes,
            exclude: $exclude
          }' > "$pending_manifest"

        # The latest link is the publication boundary. Data and verification
        # metadata are complete before it changes, so interrupted backups never
        # become the active restore candidate.
        ${pkgs.coreutils}/bin/mv "$pending_snapshot" "$completed_snapshot"
        ${pkgs.coreutils}/bin/mv "$pending_checksums" "$checksum_file"
        ${pkgs.coreutils}/bin/mv "$pending_manifest" "$manifest_file"
        ${pkgs.coreutils}/bin/ln -s "$completed_snapshot" "$pending_latest"
        ${pkgs.coreutils}/bin/mv -Tf "$pending_latest" "$latest_link"
        trap - EXIT

        if [ "$retain_count" -gt 0 ]; then
          mapfile -t snapshots_to_prune < <(
            ${pkgs.findutils}/bin/find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
              | ${pkgs.coreutils}/bin/sort -r \
              | ${pkgs.coreutils}/bin/tail -n +$((retain_count + 1))
          )

          for snapshot_name in "''${snapshots_to_prune[@]}"; do
            [ -n "$snapshot_name" ] || continue
            ${pkgs.coreutils}/bin/rm -rf "$snapshot_root/$snapshot_name"
            ${pkgs.coreutils}/bin/rm -f \
              "$manifest_root/$snapshot_name.json" \
              "$manifest_root/$snapshot_name.sha256"
          done
        fi

        echo "Hub backup completed and verified. snapshot=$completed_snapshot manifest=$manifest_file checksums=$checksum_file files=$file_count size_bytes=$size_bytes"
  '';
}
