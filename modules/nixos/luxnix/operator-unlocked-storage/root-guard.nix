# Export each generation's root-storage contract and refuse it on incompatible
# disks. Evaluation stays pure: only the target-host preflight probes hardware.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.luxnix.storage.operatorUnlocked;
  identity = cfg.rootIdentity;
  encrypted = cfg.layout == "boot-luks";
  payload = content: if content != null && content.type == "luks" then content.content else content;
  holdsRoot =
    partition:
    let
      fs = payload partition.content;
    in
    fs != null
    && (
      (fs.mountpoint or null) == "/"
      || lib.any (s: s.mountpoint == "/") (builtins.attrValues (fs.subvolumes or { }))
    );
  rootPartitions = lib.concatMap (
    disk:
    map (partition: {
      disk = disk.device;
      inherit (partition) device;
    }) (builtins.filter holdsRoot (builtins.attrValues (disk.content.partitions or { })))
  ) (builtins.attrValues (lib.attrByPath [ "disko" "devices" "disk" ] { } config));
  declared = if builtins.length rootPartitions == 1 then builtins.head rootPartitions else null;
  root = config.fileSystems."/";
  partition =
    if encrypted then
      config.boot.initrd.luks.devices.cryptroot.device
    else if declared != null then
      declared.device
    else
      root.device;
  subvolumeOf =
    fs:
    let
      option = lib.findFirst (lib.hasPrefix "subvol=") null fs.options;
    in
    if option == null then null else lib.removePrefix "subvol=" option;
  rootMounts = lib.filterAttrs (
    path: fs: fs.device == root.device || path == "/boot"
  ) config.fileSystems;
  spec = {
    version = 1;
    host = config.networking.hostName;
    inherit (cfg) layout;
    root = {
      inherit partition;
      inherit (root) fsType;
      disk =
        if identity.disk != null then
          identity.disk
        else if declared != null then
          declared.disk
        else
          null;
      mapping = if encrypted then "cryptroot" else null;
      expected_luks_uuid = identity.luksUUID;
      require_persistent_disk = identity.requirePersistentDisk;
    };
    mounts = lib.mapAttrs (_: fs: {
      inherit (fs) device fsType;
      subvolume = subvolumeOf fs;
    }) rootMounts;
    initrd = {
      systemd = config.boot.initrd.systemd.enable;
      unlocks_root = config.boot.initrd.luks.devices ? cryptroot;
      plaintext_bridge = encrypted && cfg.plaintextRootBridge;
    };
    bootloader = {
      kind =
        if lib.attrByPath [ "boot" "lanzaboote" "enable" ] false config then
          "lanzaboote"
        else if config.boot.loader.systemd-boot.enable then
          "systemd-boot"
        else
          "none";
      esp = config.boot.loader.efi.efiSysMountPoint;
      efi_variables = config.boot.loader.efi.canTouchEfiVariables;
      limit = config.boot.loader.systemd-boot.configurationLimit;
    };
  };
  sources = pkgs.runCommand "luxnix-root-guard-source" { } ''
    mkdir -p "$out"
    cp ${../../../../lx_administration/storage/root_guard.py} "$out/root_guard.py"
    cp ${../../../../lx_administration/storage/boot.py} "$out/boot.py"
    cp ${../../../../lx_administration/storage/boot_password.py} "$out/boot_password.py"
    cp ${../../../../lx_administration/storage/cutover.py} "$out/cutover.py"
    cp ${../../../../lx_administration/secret_storage.py} "$out/secret_storage.py"
  '';
  specPackage = pkgs.writeText "luxnix-root-storage.json" (builtins.toJSON spec);
  preflight = pkgs.writeShellApplication {
    name = "luxnix-root-preflight";
    runtimeInputs = [
      pkgs.python3
      pkgs.util-linux
      pkgs.cryptsetup
      pkgs.nix
    ];
    text = ''
      command="''${1:-status}"
      [ "$#" -eq 0 ] || shift
      exec python3 ${sources}/root_guard.py "$command" --spec ${specPackage} "$@"
    '';
  };
in
{
  options.luxnix.storage.operatorUnlocked = {
    plaintextRootBridge = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Let a boot-luks initrd also boot an unencrypted root. Disposable tests only: it is plaintext operation, and activation is refused once the disk is encrypted.";
    };
    rootIdentity = {
      disk = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Host fact overriding the persistent disk identity derived from the Disko layout.";
      };
      luksUUID = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Host fact pinning the root LUKS2 UUID after conversion; the preflight compares it to the live header.";
      };
      requirePersistentDisk = lib.mkOption {
        type = lib.types.bool;
        default = false;
        description = "Host fact: refuse activation when the root disk is a kernel name such as /dev/nvme0n1 instead of /dev/disk/by-id.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    environment.etc."luxnix/root-storage.json".source = specPackage;
    environment.systemPackages = [ preflight ];
    # Upstream forwards this variable through sudo, which would skip every check.
    security.sudo.extraConfig = lib.mkAfter ''
      Defaults env_keep-=NIXOS_NO_CHECK
    '';
    # NIXOS_NO_CHECK skips preSwitchChecks, so this check also sits at the entry point.
    system.systemBuilderCommands = lib.mkIf config.system.switch.enable (
      lib.mkAfter ''
        mv "$out/bin/switch-to-configuration" "$out/bin/.switch-to-configuration-unguarded"
        cat > "$out/bin/switch-to-configuration" <<GUARD
        #!${pkgs.runtimeShell}
        if [ "\''${NIXOS_NO_CHECK:-}" = 1 ]; then
          ${lib.getExe preflight} check --system "$out" --action "\$1" || exit 1
        fi
        exec "$out/bin/.switch-to-configuration-unguarded" "\$@"
        GUARD
        chmod +x "$out/bin/switch-to-configuration"
      ''
    );
    system.preSwitchChecks.rootStorage = ''
      ${lib.getExe preflight} check --system "$1" --action "$2"
    '';
  };
}
