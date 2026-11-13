# Public release artifacts only; credentials are supplied from encrypted media at runtime.
{
  pkgs,
  source,
  plan,
  diskoScript,
  closure,
  disk ? null,
  disks ? {
    system = disk;
  },
}:
let
  partitions = pkgs.lib.concatMap (d: builtins.attrValues d.content.partitions) (
    builtins.attrValues disks
  );
  isESP =
    p:
    p.type == "EF00"
    && p.content.type == "filesystem"
    && p.content.format == "vfat"
    && p.content.mountpoint == "/boot";
  isRoot =
    p:
    p.content.type == "luks"
    && p.content.name == "cryptroot"
    && p.content.initrdUnlock
    &&
      p.content.extraFormatArgs == [
        "--type"
        "luks2"
      ]
    && p.content.askPassword
    && p.content.passwordFile == null
    && p.content.keyFile == null
    && !(p.content.settings ? keyFile)
    && p.content.content.type == "btrfs";
  python = pkgs.python312.withPackages (p: [
    p.pyyaml
    p.cryptography
  ]);
  manifest = pkgs.writeText "fresh-install-plan.json" (
    builtins.toJSON (
      plan
      // {
        disko_script = diskoScript;
        partition_devices = map (p: p.device) partitions;
        config = plan.config // {
          closure = toString closure;
        };
      }
    )
  );
in
assert
  pkgs.lib.all (d: d.content.type == "gpt") (builtins.attrValues disks)
  && pkgs.lib.all (
    p:
    isESP p
    || isRoot p
    || (
      p.content.type == "luks"
      && !p.content.initrdUnlock
      &&
        p.content.extraFormatArgs == [
          "--type"
          "luks2"
        ]
      && builtins.elem p.content.content.type [
        "btrfs"
        "swap"
      ]
      && p.content.askPassword
      && p.content.passwordFile == null
      && p.content.keyFile == null
      && !(p.content.settings ? keyFile)
    )
  ) partitions
  && builtins.length (builtins.filter isESP partitions) == 1
  && builtins.length (builtins.filter isRoot partitions) == 1;
pkgs.writeShellApplication {
  name = "luxnix-install";
  runtimeInputs = [
    python
    pkgs.nixos-install-tools
    pkgs.util-linux
    pkgs.cryptsetup
    pkgs.btrfs-progs
  ];
  text = ''
    export PYTHONPATH=${source}
    exec python -m lx_administration.storage.fresh_install --plan ${manifest} "$@"
  '';
}
