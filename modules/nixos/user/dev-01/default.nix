{
  pkgs,
  config,
  lib,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.user.dev-01;
  passwordFile = "/etc/user-passwords/${cfg.name}_hashed";

in {
  options.user.dev-01 = with types; {
    name = mkOpt str "dev-01" "The name of the user's account";
    passwordFile =
      mkOpt str passwordFile
      "The hashed password file to use";
    extraGroups = mkOpt (listOf str) [] "Groups for the user to be assigned.";
    extraOptions =
      mkOpt attrs {}
      "Extra options passed to users.users.<name>";
  };

  config = {

    ##################IMPORTANT##################
    # WHEN MANUALLY CREATING A HASHED FILE IN ###
    # SHELL, WE HAVE TO ESCAPE THE $ CHARACTERS #
    #############################################

    #

    # This activation script ensures the hashed password file is present.
    # If not, it creates a default one with the given hash.
    system.activationScripts.createDefaultHashedPasswordDev01 = {
      text = ''
        set -e
        if [ ! -f ${passwordFile} ]; then
          echo "Creating default hashed password file for user ${cfg.name}"
          mkdir -p /etc/user-passwords
          # Default hashed password (as requested)
          # This is a SHA-512 crypt hash that you trust and know beforehand.
          echo "\$6\$yC9hyVoZEYLlzjbZ\$pILBYLOZBlplgoYL9L.dyIKPGPrcW2ifd1I3ffRAYIwsv8B.pA76Eo6OUq71gJJKl8kGyBsmlbKwnGcKQEpoa." > ${passwordFile}
          chmod 600 ${passwordFile}

        fi
      '';
    };


    users.users.${cfg.name} =

      {
        shell = pkgs.zsh;
        isNormalUser = true;
        initialPassword = "1";
        home = "/home/${cfg.name}";
        group = "users";
        hashedPasswordFile = passwordFile;

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
          ++ cfg.extraGroups;
      }
      // cfg.extraOptions;

    home-manager = {
      useGlobalPkgs = true;
      useUserPackages = true;
    };
  };
}
