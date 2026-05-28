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
        timestamp="$(${pkgs.coreutils}/bin/date -u +%Y%m%dT%H%M%SZ)"
        pending_snapshot="$snapshot_root/.pending-$timestamp"
        completed_snapshot="$snapshot_root/$timestamp"
        manifest_file="$manifest_root/$timestamp.json"
        previous_snapshot=""

        if [ ! -d "$runtime_root" ]; then
          echo "Skipping hub backup; runtime root missing: $runtime_root"
          exit 0
        fi

        install -d -m 0750 "$incoming_root" "$snapshot_root" "$manifest_root"
        rm -rf "$pending_snapshot"
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

        ${pkgs.coreutils}/bin/mv "$pending_snapshot" "$completed_snapshot"
        ln -sfn "$completed_snapshot" "$latest_link"

        file_count="$(${pkgs.findutils}/bin/find "$completed_snapshot" -type f | ${pkgs.coreutils}/bin/wc -l | ${pkgs.gawk}/bin/awk '{print $1}')"
        size_bytes="$(${pkgs.findutils}/bin/find "$completed_snapshot" -type f -printf '%s\n' | ${pkgs.gawk}/bin/awk '{sum += $1} END {print sum + 0}')"

        ${pkgs.jq}/bin/jq -n \
          --arg generated_at "$(${pkgs.coreutils}/bin/date -u --iso-8601=seconds)" \
          --arg hostname "$host_name" \
          --arg runtime_root "$runtime_root" \
          --arg incoming_root "$incoming_root" \
          --arg snapshot_dir "$completed_snapshot" \
          --arg latest_snapshot "$(${pkgs.coreutils}/bin/readlink -f "$latest_link")" \
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
            latest_snapshot: $latest_snapshot,
            retain_count: $retain_count,
            file_count: $file_count,
            size_bytes: $size_bytes,
            exclude: $exclude
          }' > "$manifest_file"

        if [ "$retain_count" -gt 0 ]; then
          mapfile -t snapshots_to_prune < <(
            ${pkgs.findutils}/bin/find "$snapshot_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
              | ${pkgs.coreutils}/bin/sort -r \
              | ${pkgs.coreutils}/bin/tail -n +$((retain_count + 1))
          )

          for snapshot_name in "''${snapshots_to_prune[@]}"; do
            [ -n "$snapshot_name" ] || continue
            ${pkgs.coreutils}/bin/rm -rf "$snapshot_root/$snapshot_name"
          done
        fi

        echo "Hub backup completed. snapshot=$completed_snapshot manifest=$manifest_file files=$file_count size_bytes=$size_bytes"
  '';
}
