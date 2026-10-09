{ lib, ... }:
let
  inherit (lib) mkOption types;
in
{
  options.services.luxnix.lxAnnotateLocal = {
    centerAdminBootstrap = mkOption {
      type = types.submodule {
        options = {
          username = mkOption {
            type = types.nullOr (types.strMatching "[A-Za-z0-9@.+_-]+");
            default = null;
            example = "lx_bootstrap_admin";
            description = ''
              Existing Keycloak-provisioned Django username to promote through
              the audited bootstrap_center_admin management command. Setting a
              username enables a deployment-time one-shot unit. The user must
              already have the exact synchronized center_scope:admin group.
              Clear this option after the successful bootstrap deployment.
            '';
          };
        };
      };
      default = { };
      description = "Controlled, temporary first-administrator bootstrap action.";
    };
  };
}
