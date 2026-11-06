# A second evaluation prevents the payload's closure from depending on its hash.
{ spec, runtimeSystem }:
{
  config,
  lib,
  pkgs,
  ...
}:
let
  payload = runtimeSystem.config.system.build.squashfsStore;
  manifest =
    pkgs.runCommand "migration-payload-manifest.json" { nativeBuildInputs = [ pkgs.python3 ]; }
      ''
        python - ${payload} $out <<'PY'
        import hashlib, json, os, sys
        with open(sys.argv[1], 'rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        spec = json.loads(${builtins.toJSON (builtins.toJSON spec)})
        spec['payload'] = {'sha256': digest, 'size': os.stat(sys.argv[1]).st_size}
        if spec['payload']['size'] > spec['policy']['maximum_payload_mib'] * 1024**2:
            raise SystemExit('Migration payload exceeds the reviewed RAM budget')
        with open(sys.argv[2], 'w') as stream:
            json.dump(spec, stream)
        PY
      '';
  parameters =
    pkgs.runCommand "migration-loader-parameters" { nativeBuildInputs = [ pkgs.python3 ]; }
      ''
        python - ${manifest} $out <<'PY'
        import json, shlex, sys
        spec = json.load(open(sys.argv[1]))
        values = ['/', spec['recovery']['uuid'], spec['recovery']['fstype'],
                  spec['payload']['sha256'], str(spec['payload']['size']),
                  str(spec['policy']['minimum_memory_mib']), *spec['target_serials']]
        with open(sys.argv[2], 'w') as stream:
            stream.write('load_migration_payload ' + shlex.join(values) + '\n')
        PY
      '';
in
{
  boot.initrd.systemd.enable = lib.mkForce true;
  boot.initrd.systemd.emergencyAccess = false;
  boot.initrd.systemd.additionalUpstreamUnits = [ "systemd-udev-settle.service" ];
  boot.initrd.systemd.storePaths = [
    "${./migration-load.sh}"
    "${parameters}"
  ];
  boot.initrd.supportedFilesystems = [ spec.recovery.fstype ];
  boot.initrd.luks.devices = lib.optionalAttrs (spec.recovery.luks_uuid != null) {
    migration-recovery.device = "/dev/disk/by-uuid/${spec.recovery.luks_uuid}";
  };
  boot.initrd.systemd.services.luxnix-migration-payload = {
    description = "Authenticate migration runtime in RAM";
    requiredBy = [ "sysroot-nix-.ro\\x2dstore.mount" ];
    before = [ "sysroot-nix-.ro\\x2dstore.mount" ];
    after = [
      "systemd-udev-settle.service"
      "cryptsetup.target"
    ];
    requires = [ "systemd-udev-settle.service" ];
    unitConfig.DefaultDependencies = false;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      StandardOutput = "journal+console";
      StandardError = "journal+console";
    };
    path = [
      pkgs.util-linux
      pkgs.coreutils
      pkgs.gawk
    ];
    script = ''
      . ${./migration-load.sh}
      if ! . ${parameters}; then
        echo 'Migration payload admission failed. Root conversion is unavailable.' > /dev/console
        exit 1
      fi
    '';
  };
  boot.uki.settings.UKI = {
    Initrd = lib.mkForce "${config.system.build.initialRamdisk}/initrd";
    Cmdline = lib.mkForce "init=${runtimeSystem.config.system.build.toplevel}/init ${toString config.boot.kernelParams}";
    OSRelease = lib.mkForce "@${config.system.build.migrationMetadata}";
  };
  system.build.migrationMetadata = lib.mkForce (
    pkgs.runCommand "migration-os-release" { nativeBuildInputs = [ pkgs.python3 ]; } ''
      python - ${manifest} $out <<'PY'
      import json, sys
      spec = json.load(open(sys.argv[1]))
      with open(sys.argv[2], 'w') as stream:
          stream.write('ID=luxnix-migration\nLUXNIX_MIGRATION_SPEC=' + json.dumps(json.dumps(spec)) + '\n')
      PY
    ''
  );
  system.build.migrationBundle = pkgs.runCommand "luxnix-migration-bundle" { } ''
    mkdir $out
    cp ${config.system.build.uki}/*.efi $out/migration.efi
    cp ${payload} $out/migration.squashfs
    cp ${manifest} $out/manifest.json
  '';
}
