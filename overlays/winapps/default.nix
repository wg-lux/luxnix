{ inputs, ... }:
final: _prev: {
  winapps = inputs.winapps.packages.${final.stdenv.hostPlatform.system}.winapps.overrideAttrs {
    # The fork's installer diverged from its bundled Nix patch.
    patches = [ ./setup.patch ];
  };
}
