# Apply one storage policy to host-owned hardware layouts. No runtime formatting.
{ config, lib }:
layout:
let
  enabled =
    config.luxnix.storage.operatorUnlocked.enable
    && config.luxnix.storage.operatorUnlocked.layout == "boot-luks";
  disks = layout.disko.devices.disk;
  mapping = disk: part: "lx-${disk}-${part}";
  partitions = lib.concatLists (
    lib.mapAttrsToList (
      disk: value:
      lib.mapAttrsToList (part: p: {
        inherit disk part;
        label = p.label or "disk-${disk}-${part}";
        name = mapping disk part;
      }) value.content.partitions
    ) disks
  );
  # Multi-device Btrfs must be formatted on mappings, never raw member partitions.
  rawMembers = map (p: "/dev/disk/by-partlabel/${p.label}") partitions;
  cryptMembers = map (p: "/dev/mapper/${p.name}") partitions;
  transform =
    disk: part: p:
    let
      old = p.content or null;
      fs = if old != null && old.type == "luks" then old.content else old;
      isRoot =
        fs != null
        && (
          (fs.mountpoint or "") == "/"
          || lib.any (s: (s.mountpoint or "") == "/") (builtins.attrValues (fs.subvolumes or { }))
        );
      isEfi = (p.type or "") == "EF00";
      name = if isRoot then "cryptroot" else mapping disk part;
      content =
        if fs == null then
          null
        else
          fs
          // lib.optionalAttrs (fs ? extraArgs) {
            extraArgs = map (arg: lib.replaceStrings rawMembers cryptMembers arg) fs.extraArgs;
          };
    in
    if isEfi then
      p
    else
      p
      // {
        content = {
          type = "luks";
          inherit name content;
          extraFormatArgs = [
            "--type"
            "luks2"
          ];
          initrdUnlock = isRoot;
          # Explicit Disko provisioning uses a recovery passphrase. Independent
          # runtime data keys are enrolled afterwards on the mounted encrypted root.
          settings = if isRoot && old != null && old.type == "luks" then old.settings or { } else { };

        };
      };
  transformed = lib.mapAttrs (
    disk: value:
    value
    // {
      content = value.content // {
        partitions = lib.mapAttrs (transform disk) value.content.partitions;
      };
    }
  ) disks;
in
{
  imports = layout.imports or [ ];
  config = lib.mkMerge [
    (lib.mkIf (!enabled) (builtins.removeAttrs layout [ "imports" ]))
    (lib.mkIf enabled (
      (builtins.removeAttrs layout [ "imports" ])
      // {
        disko = layout.disko // {
          devices = layout.disko.devices // {
            disk = transformed;
          };
        };
      }
    ))
  ];
}
