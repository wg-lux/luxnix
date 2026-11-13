# All legacy command names share one reserved-partition enrollment contract.
{
  optionName,
  scriptName,
}:
{
  lib,
  config,
  pkgs,
  ...
}:
let
  cfg = config.luxnix.${optionName};
  # Every command alias uses the evaluated initrd topology of this host.
  mappings = lib.mapAttrsToList (name: device: {
    inherit name;
    path = device.device;
  }) config.boot.initrd.luks.devices;
  renderer = import ./render-boot-decryption-config.nix { inherit pkgs; };
  setup = pkgs.writeShellApplication {
    name = cfg.scriptName;
    runtimeInputs = [
      pkgs.python3
      pkgs.util-linux
      pkgs.cryptsetup
    ];
    text = ''
      exec python3 ${./setup.py} \
        --offset-bytes ${toString (cfg.offsetM * 1024 * 1024)} \
        --block-size ${toString cfg.bs} --count ${toString cfg.count} \
        --renderer ${renderer}/bin/luxnix-render-boot-decryption-config \
        --output ${lib.escapeShellArg (toString cfg.configurationOutputPath)} \
        ${lib.concatMapStringsSep " \\\n        " (m: "--luks-device ${m.name} ${m.path}") mappings} "$@"
    '';
  };
in
{
  options.luxnix.${optionName} = {
    enable = lib.mkEnableOption "reserved-partition boot key enrollment";
    offsetM = lib.mkOption {
      type = lib.types.ints.unsigned;
      default = 0;
      description = "Byte offset in MiB within the dedicated reserved key partition.";
    };
    bs = lib.mkOption {
      type = lib.types.ints.positive;
      default = 1;
      description = "Key block size in bytes; total key size is bs times count.";
    };
    count = lib.mkOption {
      type = lib.types.ints.positive;
      default = 4096;
      description = "Key block count.";
    };
    scriptName = lib.mkOption {
      type = lib.types.str;
      default = scriptName;
      description = "Enrollment command name.";
    };
    configurationOutputPath = lib.mkOption {
      type = lib.types.path;
      default = "${config.luxnix.generic-settings.systemConfigurationPath}/boot-decryption-config.nix";
      description = "New configuration output path; existing files are preserved.";
    };
    # Kept as deprecated input compatibility only; neither value creates a file or mount.
    mountPoint = lib.mkOption {
      type = lib.types.str;
      default = "/mnt/usb_key";
      description = "Deprecated; dedicated key partitions are never mounted.";
    };
    keyfileName = lib.mkOption {
      type = lib.types.str;
      default = "keyfile.bin";
      description = "Deprecated; keys exist only in anonymous RAM during enrollment.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion =
          !(
            config.luxnix.storage.operatorUnlocked.enable
            && config.luxnix.storage.operatorUnlocked.layout == "boot-luks"
          );
        message = "Boot LUKS requires an operator passphrase; USB/raw-offset boot-key enrollment is retired.";
      }
    ];
    environment.systemPackages = lib.optionals (mappings != [ ]) [
      setup
      renderer
    ];
  };
}
