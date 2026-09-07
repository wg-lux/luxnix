{
  lib,
  pkgs,
  cfg,
  lxAnnotateRuntime,
  ...
}:
let
  inherit (lib) optionalString;

  runtime = lxAnnotateRuntime;
  inherit (runtime.paths) envDataDir;
  inherit (runtime.runtime) encryptedDataMountOptions;
in
{
  lxAnnotateEncryptedDataMountScript = pkgs.writeShellScriptBin "lx-annotate-encrypted-data-mount" ''
    set -euo pipefail

    mount_point="${envDataDir}"
    mapper_name="${cfg.runtime.managedEncryptedData.mapperName}"
    mapper_path="/dev/mapper/$mapper_name"
    luks_uuid="${
      if cfg.runtime.managedEncryptedData.luksUuid == null then
        ""
      else
        cfg.runtime.managedEncryptedData.luksUuid
    }"
    luks_uuid_file="${
      if cfg.runtime.managedEncryptedData.luksUuidFile == null then
        ""
      else
        toString cfg.runtime.managedEncryptedData.luksUuidFile
    }"
    key_file="${
      if cfg.runtime.managedEncryptedData.keyFile == null then
        ""
      else
        toString cfg.runtime.managedEncryptedData.keyFile
    }"

    if [ -z "$luks_uuid" ] && [ -n "$luks_uuid_file" ] && [ -f "$luks_uuid_file" ]; then
      luks_uuid="$(tr -d '\n' < "$luks_uuid_file")"
    fi

    if [ -z "$luks_uuid" ]; then
      echo "ERROR: runtime.managedEncryptedData.luksUuid is not set and no luksUuidFile was readable."
      exit 1
    fi

    if [ -z "$key_file" ] || [ ! -f "$key_file" ]; then
      echo "ERROR: encrypted data key file is missing: $key_file"
      exit 1
    fi

    install -d -m 0750 "$mount_point"

    if mountpoint -q "$mount_point"; then
      echo "Encrypted data already mounted at $mount_point"
      exit 0
    fi

    if ! cryptsetup status "$mapper_name" >/dev/null 2>&1; then
      cryptsetup open "UUID=$luks_uuid" "$mapper_name" --key-file "$key_file"
    fi

    if [ ! -b "$mapper_path" ]; then
      echo "ERROR: mapper device not available after unlock: $mapper_path"
      exit 1
    fi

    mount_cmd=(${pkgs.util-linux}/bin/mount)
    if [ -n "${cfg.runtime.managedEncryptedData.fsType}" ]; then
      mount_cmd+=(-t "${cfg.runtime.managedEncryptedData.fsType}")
    fi
    ${optionalString (encryptedDataMountOptions != "") ''
      mount_cmd+=(-o "${encryptedDataMountOptions}")
    ''}
    mount_cmd+=("$mapper_path" "$mount_point")
    "''${mount_cmd[@]}"

    chown "${cfg.runtime.managedEncryptedData.owner}:${cfg.runtime.managedEncryptedData.group}" "$mount_point"
    chmod "${cfg.runtime.managedEncryptedData.dirMode}" "$mount_point"
  '';

  lxAnnotateEncryptedDataUmountScript = pkgs.writeShellScriptBin "lx-annotate-encrypted-data-umount" ''
    set -euo pipefail

    mount_point="${envDataDir}"
    mapper_name="${cfg.runtime.managedEncryptedData.mapperName}"

    if mountpoint -q "$mount_point"; then
      ${pkgs.util-linux}/bin/umount "$mount_point"
    fi

    if cryptsetup status "$mapper_name" >/dev/null 2>&1; then
      cryptsetup close "$mapper_name"
    fi
  '';
}
