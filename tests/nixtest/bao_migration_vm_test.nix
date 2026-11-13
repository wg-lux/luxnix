{ repoRoot, ... }:
{
  name = "bao-migration";
  nodes.server = { pkgs, ... }: {
    virtualisation.memorySize = 2048;
    environment = {
      systemPackages = [
        (import pkgs.path {
          inherit (pkgs.stdenv.hostPlatform) system;
          config.allowUnfree = true;
        }).vault
        pkgs.openbao
        pkgs.openssl
        (pkgs.python3.withPackages (p: [ p.pyyaml ]))
      ];
      variables.PYTHONPATH = "${repoRoot}";
      etc."migration-guest.py".source = ./bao_migration_guest.py;
    };
    system.stateVersion = "26.05";
  };
  testScript = ''
    server.start()
    server.wait_for_unit("multi-user.target")
    server.succeed("python /etc/migration-guest.py", timeout=180)
  '';
}
