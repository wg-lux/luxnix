{ pkgs
, config
, lib
, ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.admin;
  sslCertGroupName = config.users.groups.sslCert.name;
  passwordFile = config.luxnix.vault.adminPasswordHashedFile;
  sensitiveServicesGroupName = config.luxnix.generic-settings.sensitiveServiceGroupName;

  # passwordFile = "/etc/user-passwords/${cfg.name}_hashed";
in
{
  options.user.admin = with types; {
    name = mkOpt str "admin" "The name of the user's account";
    passwordFile =
      mkOpt str passwordFile
        "The hashed password file to use";
    extraGroups = mkOpt (listOf str) [ ] "Groups for the user to be assigned.";
    extraOptions =
      mkOpt attrs { }
        "Extra options passed to users.users.<name>";
  };

  config = {
    system.activationScripts.createDefaultHashedPasswordAdmin = {
      text = ''
        set -e
        if [ ! -f ${passwordFile} ]; then
          echo "Creating default hashed password file for user ${cfg.name}"
          mkdir -p /etc/secrets/vault
          # Default hashed password (as requested)
          # This is a SHA-512 crypt hash that you trust and know beforehand.
          # theater-chief
          echo "\$6\$yC9hyVoZEYLlzjbZ\$pILBYLOZBlplgoYL9L.dyIKPGPrcW2ifd1I3ffRAYIwsv8B.pA76Eo6OUq71gJJKl8kGyBsmlbKwnGcKQEpoa." > ${passwordFile}
          chmod 600 ${passwordFile}

        fi
      '';
    };
    users.users.${cfg.name} =
      {
        shell = pkgs.zsh;
        isNormalUser = true;
        hashedPasswordFile = passwordFile;
        home = "/home/${cfg.name}";
        group = "users";
        linger = true; # Makes sure user services start at boot not at login

        # TODO: set in modules
        extraGroups =
          [
            "wheel"
            "audio"
            "sound"
            "video"
            "networkmanager"
            "input"
            "tty"
            "podman"
            "kvm"
            "libvirtd"
          ]
          ++ [
            sslCertGroupName
            sensitiveServicesGroupName
          ]
          ++ cfg.extraGroups;
      }
      // cfg.extraOptions;

    home-manager = {
      # modified due to this warning: evaluation warning: admin profile: You have set either `nixpkgs.config` or `nixpkgs.overlays` while using `home-manager.useGlobalPkgs`.
      useGlobalPkgs = false;
      useUserPackages = true;
    };
  };
}
