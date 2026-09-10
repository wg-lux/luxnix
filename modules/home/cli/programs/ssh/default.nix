{
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.cli.programs.ssh;
in
{
  options.cli.programs.ssh = with types; {
    enable = mkBoolOpt false "Whether or not to enable ssh";
    keychain = {
      enable = mkBoolOpt true "Whether to enable keychain for SSH keys.";
      keys = mkOpt (listOf str) [ "id_ed25519" ] "SSH private key names for keychain to load.";
    };

    extraHosts = lib.mkOption {
      type = lib.types.attrsOf (
        lib.types.submodule {
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
        }
      );
      default = { };
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
    programs.keychain = mkIf (cfg.keychain.enable && cfg.keychain.keys != [ ]) {
      enable = true;
      enableXsessionIntegration = true;
      enableZshIntegration = true;
      keys = cfg.keychain.keys;
      # agents = [ "ssh" ];
    };

    programs.ssh = {

      matchBlocks = {
        enableDefaultConfig = false;
        "*" = {
          enable = true;
          forwardAgent = false;
          userKnownHostsFile = "~/.ssh/known_hosts";
          addKeysToAgent = "yes";
          compression = false;
          serverAliveInterval = 0;
          serverAliveCountMax = 3;
          hashKnownHosts = false;
          controlMaster = "no";
          controlPath = "~/.ssh/master-%r@%n:%p";
          controlPersist = "no";
        };
      }
      // cfg.extraHosts;
    };
  };
}
