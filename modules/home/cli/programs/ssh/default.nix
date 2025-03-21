{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.cli.programs.ssh;
in {
  options.cli.programs.ssh = with types; {
    enable = mkBoolOpt false "Whether or not to enable ssh";

    extraHosts = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule {
        options = {
          hostname = lib.mkOption {
            type = lib.types.str;
            description = "The hostname or IP address of the SSH host.";
          };
          identityFile = lib.mkOption {
            type = lib.types.str;
            description = "The path to the identity file for the SSH host.";
          };
        };
      });
      default = {};
      description = "A set of extra SSH hosts.";
      example = literalExample ''
        {
          "gitlab-personal" = {
            hostname = "gitlab.com";
            identityFile = "~/.ssh/id_ed25519_personal";
          };
        }
      '';
    };
  };

  config = mkIf cfg.enable {
    programs.keychain = {
      enable = true;
      keys = ["id_ed25519"];
      agents = ["ssh"];
    };

    programs.ssh = {
      enable = true;
      addKeysToAgent = "yes";
      matchBlocks = cfg.extraHosts;
    };
  };
}
