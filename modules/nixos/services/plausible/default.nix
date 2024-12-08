{
  config,
  lib,
  ...
}:
# CHANGEME Maybe in Future
with lib;
with lib.luxnix; let
  cfg = config.services.luxnix.plausible;
in {
  # options.services.luxnix.plausible = {
  #   enable = mkBoolOpt false "Enable the plausible service";
  # };

  # config = mkIf cfg.enable {
  #   sops.secrets.plausible_admin_password = {
  #     sopsFile = ../secrets.yaml;
  #   };

  #   sops.secrets.plausible_secret_keybase_file = {
  #     sopsFile = ../secrets.yaml;
  #   };

  #   services = {
  #     plausible = {
  #       enable = true;
  #       server = {
  #         baseUrl = "https://plausible.haseebmajid.dev";
  #         port = 8455;
  #         secretKeybaseFile = config.sops.secrets.plausible_secret_keybase_file.path;
  #       };
  #       adminUser = {
  #         email = "hello@haseebmajid.dev";
  #         passwordFile = config.sops.secrets.plausible_admin_password.path;
  #         activate = true;
  #       };
  #     };

  #     cloudflared = {
  #       enable = true;
  #       tunnels = {
  #         "ec0b6af0-a823-4616-a08b-b871fd2c7f58" = {
  #           ingress = {
  #             "plausible.haseebmajid.dev" = "http://localhost:8455";
  #           };
  #         };
  #       };
  #     };
  #   };
  # };
}
