{ nixpkgs }:
let
  system = "x86_64-linux";
  pkgs = import nixpkgs { inherit system; };
  recoveryScript = pkgs.writeShellApplication {
    name = "gc-02-offline-recovery";
    runtimeInputs = with pkgs; [
      btrfs-progs
      cryptsetup
      coreutils
      findutils
      util-linux
      systemd
    ];
    text = builtins.readFile ./gc-02-offline-recovery.sh;
  };
in
(nixpkgs.lib.nixosSystem {
  inherit system;
  modules = [
    "${nixpkgs.outPath}/nixos/modules/installer/cd-dvd/installation-cd-minimal.nix"
    (_: {
      networking.hostName = "gc-02-recovery";
      isoImage.isoName = "gc-02-storage-recovery.iso";
      environment.systemPackages = [ recoveryScript ];
      boot.supportedFilesystems = [ "btrfs" ];

      # The installer ISO autologins root. Start the guarded recovery workflow
      # once on its first interactive shell; destructive work still requires
      # an exact typed confirmation and the installed disk's LUKS credential.
      environment.interactiveShellInit = ''
        if [ "$(tty 2>/dev/null || true)" = /dev/tty1 ] && [ ! -e /run/gc-02-recovery-started ]; then
          touch /run/gc-02-recovery-started
          gc-02-offline-recovery
        fi
      '';
    })
  ];
}).config.system.build.isoImage
