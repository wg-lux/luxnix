{
  lib,
  config,
  inputs,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.nix-index;
in {
  options.cli.programs.nix-index = with types; {
    enable = mkBoolOpt false "Whether or not to nix index";
  };

  imports = with inputs; [
    nix-index-database.hmModules.nix-index
  ];

  config = mkIf cfg.enable {
    programs.nix-index = {
      enable = true;
      enableBashIntegration = true;
    };
    programs.nix-index-database.comma.enable = false; #FIX BORKEN error: collision between `/nix/store/9c4vrjmq05jcbhp7mkb6swhyhikvvfyi-nix-index-with-full-db-0.1.8/share/cache/nix-index/files' and `/nix/store/6pzvnpinvd5bifdlmni0wls9r907v9vc-comma-with-db-1.9.0/share/cache/nix-index/files'
  };
}
