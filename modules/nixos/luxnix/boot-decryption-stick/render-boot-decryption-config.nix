{ pkgs }:
pkgs.writeShellApplication {
  name = "luxnix-render-boot-decryption-config";
  runtimeInputs = [
    pkgs.coreutils
    pkgs.nixfmt
  ];
  text = builtins.readFile ./render-boot-decryption-config.sh;
}
