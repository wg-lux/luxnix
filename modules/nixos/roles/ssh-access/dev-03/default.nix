{ pkgs
, lib
, config
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.ssh-access.dev-03;
in
{
  options.roles.ssh-access.dev-03 = {
    enable = mkBoolOpt false ''
      Enable ssh access for dev-03 (defaults to gc-08 pub key)
    '';

    idEd25519 = mkOption {
      type = types.str;
      # Vault-sourced key (master-vault/identities/users/dev_03/id_ed25519.pub)
      # Overridden fleet-wide via group_roles.ssh-access.dev-03.idEd25519 in all.yml
      # Old key (pre-vault): AAAAC3NzaC1lZDI1NTE5AAAAIDBJcYjGNIwOUs+KG8TbBxPWtJFEqni0p+1J5Yz++Aos
      default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDmbrNEa3Ez0LrIeg5dY+/OrFQxG2k7/2skc5Extz/eK dev_03@lx-secrets";
      description = ''
        Access key for user HZ
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
