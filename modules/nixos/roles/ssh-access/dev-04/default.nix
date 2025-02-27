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
      Enable ssh access for dev-04 (defaults to gc-08 pub key)
    '';

    idEd25519 = mkOption {
      type = types.str;
      default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK";
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
