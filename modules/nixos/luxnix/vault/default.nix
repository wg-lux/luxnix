# Vault server, client enrollment and hub PKI.
#
# context.nix holds shared settings. Each tools/ file adds the scripts of one
# domain and may use the context plus every tools/ file listed before it.
# options.nix and config.nix receive the complete context.
{
  lib,
  pkgs,
  config,
  ...
}:
let
  args = { inherit lib pkgs config; };
  ctx =
    lib.foldl' (acc: file: acc // import file (args // { ctx = acc; })) (import ./context.nix args)
      [
        ./tools/auth.nix
        ./tools/server.nix
        ./tools/hub-pki.nix
        ./tools/hub-sites.nix
        ./tools/client.nix
      ];
in
{
  options.luxnix.vault = import ./options.nix (args // { inherit ctx; });
  config = import ./config.nix (args // { inherit ctx; });
}
