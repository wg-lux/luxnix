{
  pkgs,
  lib,
  config,
  host,
  ...
}:
with lib;
with lib.luxnix; let
  cfg = config.clone-dirs;
  repos = { #FIXME: remove hardcoded references
    "https://github.com/wg-lux/luxnix" = "/home/admin/luxnix";
    "https://github.com/wg-lux/endoreg-db-api" = "/home/admin/dev/endoreg-db-api";
    "https://github.com/wg-lux/endoreg-db" = "/home/admin/dev/endoreg-db";
    "https://github.com/wg-lux/nix-config" = "/home/admin/repotest/nix-config";
  };
in {
  options.clone-dirs = with types; {
    enable = mkBoolOpt true "enable default git repo cloning";
  };

  config = mkIf cfg.enable {

    home.activation.cloneRepos = lib.mkAfter ''
      ${pkgs.git}/bin/git --version > /dev/null || exit 1

      repos='${builtins.toJSON repos}'

      echo "$repos" | ${pkgs.jq}/bin/jq -c 'to_entries[]' | while read -r entry; do
        url=$(echo "$entry" | ${pkgs.jq}/bin/jq -r '.key' <<< "$entry")
        path=$(echo "$entry" | ${pkgs.jq}/bin/jq -r '.value' <<< "$entry")

        if [ ! -d "$(dirname "$path")" ]; then
          mkdir -p "$(dirname "$path")"
        fi

        if [ ! -d "$path" ]; then
          ${pkgs.git}/bin/git clone -- "$url" "$path"
        else
          echo "$path already exists, skipping clone."
        fi
      done
    '';

  };
}