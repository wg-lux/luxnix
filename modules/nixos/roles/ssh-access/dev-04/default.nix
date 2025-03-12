{ pkgs
, lib
, config
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.ssh-access.dev-04;
in
{
  options.roles.ssh-access.dev-04 = {
    enable = mkBoolOpt false ''
      Enable ssh access for dev-04 
    '';

    idEd25519 = mkOption {
      type = types.str;
      default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICSpoZVcX+K6NdrfqcUVPTU8Ljqlp83YDzzEHjTHU2NO";
      description = ''
        Access key for user
      '';
    };
  };

  config = mkIf cfg.enable {
    services.ssh.authorizedKeys = [
      # TODO make dedicated authorizedDevKeys option which grants access to dev user
      "${cfg.idEd25519}"
    ];
  };
}
