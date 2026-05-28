{
  lib,
  pkgs,
  config,
  ...
}:
with lib;
with lib.luxnix;
let
  cfg = config.roles.development;
  nixdFlakeExpr = ''
    let
      flakePath = builtins.getEnv "LUXNIX_FLAKE";
    in
      builtins.getFlake (
        if flakePath != "" then flakePath else builtins.toString ./.
      )
  '';
  nixdHostExpr = ''
    let
      host = builtins.getEnv "LUXNIX_HOST";
    in
      if host != "" then
        host
      else
        builtins.replaceStrings [ "\n" ] [ "" ] (builtins.readFile /etc/hostname)
  '';
in
{
  options.roles.development = {
    enable = mkBoolOpt false "Enable development configuration";
  };

  config = mkIf cfg.enable {
    roles.desktop.enable = true;

    cli = {

      programs = {
        db.enable = true;
        direnv.enable = true;
        eza.enable = true;
        fzf.enable = true;
        git.enable = true;
        htop.enable = true;
        modern-unix.enable = true;
        network-tools.enable = true;
        nix-index.enable = true;
        podman.enable = false;
        ssh.enable = true;
        starship.enable = true;
        yazi.enable = true;
        zoxide.enable = true;
      };
      terminals.tmux.enable = true;
    };

    programs.nixvim = {
      extraPackages = [
        pkgs.nixfmt-rfc-style
      ];

      lsp.servers.nixd = {
        enable = true;
        package = pkgs.nixd;
        config = {
          cmd = [ "nixd" ];
          filetypes = [ "nix" ];
          root_markers = [
            "flake.nix"
            ".git"
          ];
          settings.nixd = {
            nixpkgs.expr = ''
              import (${nixdFlakeExpr}).inputs.nixpkgs { }
            '';
            formatting.command = [ "nixfmt" ];
            options = {
              nixos.expr = ''
                let
                  flake = ${nixdFlakeExpr};
                  host = ${nixdHostExpr};
                  configName =
                    if builtins.hasAttr host flake.nixosConfigurations then
                      host
                    else
                      "gc-02";
                in
                  (builtins.getAttr configName flake.nixosConfigurations).options
              '';
              home-manager.expr = ''
                let
                  flake = ${nixdFlakeExpr};
                  host = ${nixdHostExpr};
                  userEnv = builtins.getEnv "USER";
                  userName = if userEnv != "" then userEnv else "admin";
                  homeName = userName + "@" + host;
                  adminHomeName = "admin@" + host;
                  configName =
                    if builtins.hasAttr homeName flake.homeConfigurations then
                      homeName
                    else if builtins.hasAttr adminHomeName flake.homeConfigurations then
                      adminHomeName
                    else
                      "admin@gc-02";
                in
                  (builtins.getAttr configName flake.homeConfigurations).options
              '';
            };
          };
        };
      };
    };
  };
}
