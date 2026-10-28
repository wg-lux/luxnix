{ repoRoot, ... }:
{
  name = "openbao-local";
  nodes = {
    server =
      {
        lib,
        pkgs,
        ...
      }:
      let
        # Only this disposable fixture replaces platform admission. Production
        # binaries have no option to accept swtpm or disabled Secure Boot.
        testClient = pkgs.writeText "openbao-local-test-client.py" ''
          import runpy
          globals().update(runpy.run_path("${repoRoot + "/lx_administration/storage/openbao_local.py"}"))
          def platform_preflight():
              status = platform_status()
              assert status["tpm2"], "fixture requires a usable software TPM"
              return status
        '';
      in
      {
        imports = [
          (repoRoot + "/modules/nixos/luxnix/openbao")
          (repoRoot + "/modules/nixos/luxnix/operator-unlocked-storage")
        ];
        virtualisation = {
          tpm.enable = true;
          # UEFI firmware reports the TPM, so `systemd-creds has-tpm2` passes fully.
          useEFIBoot = true;
          memorySize = 2048;
        };
        luxnix.openbao.local.enable = true;
        luxnix.storage.operatorUnlocked = {
          enable = true;
          unlockMethod = "local-openbao";
          migration.enable = false;
          volumes.test = {
            container = "/var/lib/test.luks";
            mountPoint = "/var/lib/test-volume";
            luksUUID = "11111111-1111-1111-1111-111111111111";
          };
          volumes.fresh = {
            container = "/var/lib/fresh.luks";
            mountPoint = "/var/lib/fresh-volume";
            luksUUID = "33333333-3333-3333-3333-333333333333";
            minimumSizeMiB = 64;
          };
        };
        # The disposable guest boots before enrollment; production hosts only
        # activate this profile after the pre-switch gate passes.
        systemd.services.openbao-local.wantedBy = lib.mkForce [ ];
        systemd.services.openbao-local-preflight.serviceConfig.ExecStart = lib.mkForce (
          pkgs.writeShellScript "openbao-local-test-preflight" ''
            set -eu
            export PATH=${
              lib.makeBinPath [
                pkgs.systemd
                pkgs.util-linux
              ]
            }
            ${pkgs.python3}/bin/python ${repoRoot + "/lx_administration/secret_storage.py"} --allow-runtime /run
            exec ${pkgs.python3}/bin/python ${
              repoRoot + "/lx_administration/storage/openbao_local.py"
            } /var/lib/openbao-bootstrap/seal.cred
          ''
        );
        environment = {
          systemPackages = [
            pkgs.python3
            pkgs.cryptsetup
            pkgs.e2fsprogs
          ];
          etc = {
            "local-client.py".source = repoRoot + "/lx_administration/storage/openbao_local.py";
            "test-client.py".source = testClient;
            "local-guest.py".source = ./openbao_local_guest.py;
            "migration.py".source = repoRoot + "/lx_administration/storage/operator_migration.py";
            "cutover.py".source = repoRoot + "/lx_administration/storage/cutover.py";
            "enrollment.py".source = repoRoot + "/lx_administration/storage/openbao_enroll.py";
          };
        };
        system.stateVersion = "26.05";
      };
    other = { pkgs, ... }: {
      virtualisation.tpm.enable = true;
      environment.systemPackages = [ pkgs.python3 ];
      system.stateVersion = "26.05";
    };
  };
  testScript = ''
    start_all()
    server.wait_for_unit("multi-user.target")
    other.wait_for_unit("multi-user.target")
    server.fail("systemctl start openbao-local.service")
    with subtest("production enrollment rejects the software TPM without mutations"):
        server.fail("luxnix-openbao-local preflight > /run/preflight.out 2>&1")
        server.succeed("cat /run/preflight.out; grep tpm-not-physical /run/preflight.out")
        server.fail("test -e /var/lib/openbao-bootstrap/seal.cred")
    server.succeed("python /etc/local-guest.py prepare")
    server.fail("python /etc/local-client.py /run/local-test/host.cred")
    server.fail("python /etc/local-client.py /run/local-test/pcr0.cred")

    with subtest("enrollment with explicitly isolated platform fixture"):
        server.succeed("python /etc/local-guest.py enroll")
        server.succeed("python /etc/local-client.py /var/lib/openbao-bootstrap/seal.cred")
        server.succeed("python /etc/local-client.py /var/lib/openbao-bootstrap/volume-unlock.cred")
        server.succeed("test -z \"$(ss -ltnH 'sport = :8310 or sport = :8311')\"")

    with subtest("a copied store credential does not unseal on another TPM"):
        # Ciphertext only crosses the driver; plaintext stays inside the disposable guest.
        server.succeed("cp /var/lib/openbao-bootstrap/seal.cred /tmp/shared/copied.cred")
        other.succeed("cp /tmp/shared/copied.cred /run/copied.cred")
        other.fail("systemd-creds decrypt --name=seal.key /run/copied.cred /dev/null")

    with subtest("existing container adopted without data or UUID change"):
        server.succeed("python /etc/local-guest.py adopt")
        server.succeed("python /etc/local-guest.py verify")

    with subtest("new volume provisioning and repeat preserve OpenBao keyslots"):
        server.succeed("python /etc/local-guest.py provision")
        server.succeed("systemctl start luxnix-storage-unlock-fresh")
        server.succeed("cryptsetup close fresh")

    with subtest("boot unlock unit uses only the AppRole credential"):
        server.succeed("systemctl start luxnix-storage-unlock-test")
        server.succeed("python /etc/local-guest.py check-data")
        server.succeed("cryptsetup close test")
        server.succeed("systemctl restart openbao-local")
        server.succeed("systemctl start luxnix-storage-unlock-test")
        server.succeed("cryptsetup close test")

    with subtest("unlock credential rotation"):
        server.succeed("python /etc/local-guest.py rotate")
        server.succeed("systemctl start luxnix-storage-unlock-test")
        server.succeed("python /etc/local-guest.py check-data")
        server.succeed("cryptsetup close test")

    with subtest("sealed or missing store fails closed without fallback"):
        server.succeed("systemctl stop openbao-local")
        server.succeed("mv /var/lib/openbao-local/raft/raft.db /var/lib/openbao-local/raft/saved.db")
        server.fail("systemctl start openbao-local")
        server.fail("systemctl start luxnix-storage-unlock-test")
        server.fail("test -e /dev/mapper/test")
        server.succeed("mv /var/lib/openbao-local/raft/saved.db /var/lib/openbao-local/raft/raft.db")
        server.succeed("systemctl reset-failed; systemctl start luxnix-storage-unlock-test")
        server.succeed("cryptsetup close test")
  '';
}
