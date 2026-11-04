# Apply one storage policy to host-owned hardware layouts. No runtime formatting.
{ config, lib }:
layout:
let
  enabled =
    config.luxnix.storage.operatorUnlocked.enable
    && config.luxnix.storage.operatorUnlocked.layout == "boot-luks";
  disks = layout.disko.devices.disk;
  encryptedPartition =
    p: (p.type or "") != "EF00" && ((p.content or null) == null || p.content.type != "mdraid");
  filesystem =
    content: if content != null && content.type == "luks" then content.content else content;
  mounts =
    fs:
    lib.filter (p: p != null) (
      [ (fs.mountpoint or null) ]
      ++ map (s: s.mountpoint or null) (builtins.attrValues (fs.subvolumes or { }))
    );
  # Names describe the storage role, never a hostname, controller or disk identifier.
  roleName =
    fs:
    if builtins.elem "/" (mounts fs) then
      "cryptroot"
    else if fs.type == "swap" then
      "cryptswap"
    else if builtins.elem "/var/lib/lx-annotate" (mounts fs) then
      "luxnix-app-storage"
    else if mounts fs != [ ] then
      "luxnix-data-${
        lib.replaceStrings [ "/" ] [ "-" ] (
          lib.removePrefix "/" (
            builtins.head (lib.sort (a: b: builtins.stringLength a < builtins.stringLength b) (mounts fs))
          )
        )
      }"
    else
      throw "Encrypted data filesystem needs a mountpoint to derive its shared mapper name";
  partitions = lib.concatLists (
    lib.mapAttrsToList (
      disk: value:
      lib.mapAttrsToList (part: p: {
        encrypted = encryptedPartition p;
        content = filesystem (p.content or null);
        path = "/dev/disk/by-partlabel/${p.label or "disk-${disk}-${part}"}";
      }) value.content.partitions
    ) disks
  );
  # Multi-device Btrfs must be formatted on mappings, never raw member partitions.
  memberMappings = lib.concatMap (
    p:
    lib.optionals (p.content != null) (
      lib.imap1 (index: path: {
        inherit path;
        name = "${roleName p.content}-member-${toString index}";
      }) (lib.filter (arg: lib.hasPrefix "/dev/disk/by-partlabel/" arg) (p.content.extraArgs or [ ]))
    )
  ) partitions;
  partitionName =
    p:
    if p.content != null then
      roleName p.content
    else
      (lib.findFirst (
        member: member.path == p.path
      ) (throw "Unowned encrypted member ${p.path}; declare its filesystem owner") memberMappings).name;
  payloadPartitions = lib.filter (p: p.encrypted) partitions;
  names =
    map partitionName payloadPartitions
    ++ lib.mapAttrsToList (_: array: roleName (filesystem array.content)) (
      lib.filterAttrs (_: array: (array.content or null) != null) (layout.disko.devices.mdadm or { })
    );
  rawMembers = map (p: p.path) payloadPartitions;
  cryptMembers = map (p: "/dev/mapper/${partitionName p}") payloadPartitions;
  encrypt =
    mappingName: old:
    let
      fs = filesystem old;
      name = mappingName;
      isRoot = name == "cryptroot";
      content =
        if fs == null then
          null
        else
          fs
          // lib.optionalAttrs (fs ? extraArgs) {
            extraArgs = map (arg: lib.replaceStrings rawMembers cryptMembers arg) fs.extraArgs;
          };
    in
    {
      type = "luks";
      inherit name content;
      extraFormatArgs = [
        "--type"
        "luks2"
      ];
      initrdUnlock = isRoot;
      # Provision with a recovery credential; enroll data keys on encrypted root.
      settings = { };
    };
  transform =
    disk: part: p:
    if !encryptedPartition p then
      p
    else
      p
      // {
        content = encrypt (partitionName {
          content = filesystem (p.content or null);
          path = "/dev/disk/by-partlabel/${p.label or "disk-${disk}-${part}"}";
        }) (p.content or null);
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
        assertions = (layout.assertions or [ ]) ++ [
          {
            assertion = builtins.length names == builtins.length (lib.unique names);
            message = "Encrypted storage roles must have unique mapper names; use distinct mountpoints for separate data filesystems.";
          }
        ];
        disko = layout.disko // {
          devices = layout.disko.devices // {
            disk = transformed;
            # MD assembles raw members first; one LUKS mapping covers each array.
            mdadm = lib.mapAttrs (
              _: array:
              array
              // lib.optionalAttrs ((array.content or null) != null) {
                content = encrypt (roleName (filesystem array.content)) array.content;
              }
            ) (layout.disko.devices.mdadm or { });
          };
        };
      }
    ))
  ];
}
