# Minimal bootable recovery media. It contains storage tools and the LuxNix recovery
# command only, so recovery never depends on building a host or its applications.
{
  nixpkgs,
  system,
  repoRoot,
}:
let
  tool =
    pkgs:
    let
      sources = pkgs.runCommand "luxnix-boot-recover-source" { } ''
        mkdir -p "$out"
        cp ${repoRoot + "/lx_administration/storage/root_recovery.py"} "$out/root_recovery.py"
        cp ${repoRoot + "/lx_administration/storage/root_guard.py"} "$out/root_guard.py"
        cp ${repoRoot + "/lx_administration/storage/boot_password.py"} "$out/boot_password.py"
        cp ${repoRoot + "/lx_administration/storage/boot.py"} "$out/boot.py"
        cp ${repoRoot + "/lx_administration/storage/cutover.py"} "$out/cutover.py"
        cp ${repoRoot + "/lx_administration/secret_storage.py"} "$out/secret_storage.py"
      '';
    in
    pkgs.writeShellApplication {
      name = "luxnix-boot-recover";
      runtimeInputs = [
        pkgs.python3
        pkgs.util-linux
        pkgs.cryptsetup
        pkgs.btrfs-progs
        pkgs.nix
      ];
      text = ''
        exec python3 ${sources}/root_recovery.py "$@"
      '';
    };
  image = nixpkgs.lib.nixosSystem {
    inherit system;
    modules = [
      "${nixpkgs}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
      (
        { pkgs, ... }:
        {
          boot.zfs.forceImportRoot = false;
          environment.systemPackages = [
            (tool pkgs)
            pkgs.cryptsetup
            pkgs.btrfs-progs
          ];
          isoImage.appendToMenuLabel = " LuxNix boot recovery";
        }
      )
    ];
  };
in
{
  recoverTool = tool nixpkgs.legacyPackages.${system};
  iso = image.config.system.build.isoImage;
}
