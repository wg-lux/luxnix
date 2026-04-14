{
  pkgs,
  lib,
  config,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.roles.ssh-access.dev-01;
in {
  options.roles.ssh-access.dev-01 = {
    enable = mkBoolOpt false ''
      Enable ssh access for dev-01 (defaults to gc-02 pub key)
    '';

    idEd25519 = mkOption {
      type = types.str;
      # Vault-sourced key (master-vault/identities/users/dev_01/id_ed25519.pub)
      # Overridden fleet-wide via group_roles.ssh-access.dev-01.idEd25519 in all.yml
      # Old key (pre-vault): AAAAC3NzaC1lZDI1NTE5AAAAIEh2Bg+mSSvA80ALScpb81Q9ZaBFdacdxJZtAfZpwYkK
      default = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMz6afkjO9Y5cEebfeGl6qMH/q/YnYl7XNuY66fo/Bs3 dev_01@lx-secrets";
      description = ''
        Access key for user
      '';
    };
  };

  config = mkIf cfg.enable {
    services.ssh.authorizedKeys = [
      "${cfg.idEd25519}"
    ];
  };
}
