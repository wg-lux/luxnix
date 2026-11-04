{
  config,
  lib,
  pkgs,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.desktop.addons.plasma;
  storage = attrByPath [ "luxnix" "storage" "operatorUnlocked" ] { } config;
  # Derived on every rebuild: only boot-LUKS hosts type a root passphrase at boot,
  # and the pre-switch check refuses to activate this on an unencrypted root.
  bootLuks = (storage.enable or false) && (storage.layout or null) == "boot-luks";
  # Hosts without a client account keep the normal SDDM password login.
  walletUnlock = cfg.enable && bootLuks && config.user.client.enable;
in
{
  options.roles.desktop.addons.plasma = with types; {
    enable = mkBoolOpt false "Enable or disable the plasma DE.";
  };

  config = mkIf cfg.enable (mkMerge [
    (mkIf walletUnlock {
      assertions = [
        {
          assertion = !(storage.remoteUnlock.enable or false);
          message = "Boot-LUKS desktop autologin must not follow a remote SSH disk unlock: it would leave an unattended session open.";
        }
      ];
      # The root passphrase typed at the Plymouth prompt is the login: SDDM logs in
      # the client user and KWallet opens with the same passphrase from the kernel keyring.
      services.displayManager.autoLogin = {
        enable = true;
        user = config.user.client.name;
      };
      systemd.services.display-manager.serviceConfig.KeyringMode = "inherit";
      security.pam.services.sddm-autologin.rules.auth = {
        systemd_loadkey = {
          order = 10050;
          control = "optional";
          modulePath = "${config.systemd.package}/lib/security/pam_systemd_loadkey.so";
        };
        kwallet = {
          order = 10400;
          control = "optional";
          modulePath = "${pkgs.kdePackages.kwallet-pam}/lib/security/pam_kwallet5.so";
        };
      };
    })
    {
      ###
      roles.custom-packages.kdePlasma = true;

      services = {
        desktopManager.plasma6.enable = true;
        displayManager = {
          defaultSession = "plasma"; # Correct session name for Plasma Wayland
          gdm = {
            enable = false;
            autoSuspend = false;
          };
          sddm = {
            enable = true;
            wayland.enable = true; # Forces the SDDM greeter to use Wayland
          };
        };
        xserver = {
          enable = true;
          # TODO (desktop-role owner): derive the keyboard layout from the locale
          # contract after generic-settings exports a dedicated XKB layout.
          xkb.layout = "de";
          xkb.variant = "";

        };
      };
    }
  ]);
}
