# Disposable installer rehearsal: explicit plain root, unavailable protected data.
{
  pkgs,
  disko,
  repoRoot,
}:
let
  sshFixtures = pkgs.path + "/nixos/tests/initrd-network-ssh";
in
disko.lib.testLib.makeDiskoTest {
  inherit pkgs;
  name = "unencrypted-storage";
  disko-config =
    { lib, ... }:
    (lib.evalModules {
      modules = [
        { options.disko = lib.mkOption { type = lib.types.attrs; }; }
        (
          (import "${repoRoot}/systems/x86_64-linux/encrypted-layout.nix" {
            inherit lib;
            config.luxnix.storage.operatorUnlocked = {
              enable = true;
              layout = "unencrypted-root";
            };
          })
          {
            disko.devices.disk.system = {
              type = "disk";
              device = "/dev/vda";
              content = {
                type = "gpt";
                partitions = {
                  ESP = {
                    size = "256M";
                    type = "EF00";
                    content = {
                      type = "filesystem";
                      format = "vfat";
                      mountpoint = "/boot";
                    };
                  };
                  root = {
                    size = "100%";
                    # Deliberately start with an old encrypted declaration; explicit
                    # selection must render plain provisioning without a disk credential.
                    content = {
                      type = "luks";
                      name = "original-root";
                      content = {
                        type = "filesystem";
                        format = "ext4";
                        mountpoint = "/";
                      };
                    };
                  };
                };
              };
            };
          }
        )
      ];
    }).config;
  extraSystemConfig = { lib, pkgs, ... }: {
    imports = [ "${repoRoot}/modules/nixos/luxnix/operator-unlocked-storage" ];
    options = {
      luxnix.storage.loginAccess.enable = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
      luxnix.vault.server.managedTls.encryptedStorage = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
      services.luxnix.lxAnnotateLocal.runtime.managedEncryptedData.enable = lib.mkOption {
        type = lib.types.bool;
        default = false;
      };
    };
    config = {
      luxnix.storage.operatorUnlocked = {
        enable = true;
        layout = "unencrypted-root";
        migration.enable = false;
        volumes.protected = {
          container = "/var/lib/luxnix-storage/not-provisioned.img";
          luksUUID = "5c57c24c-9c73-4f77-81f7-d0404e957644";
          mountPoint = "/srv/protected";
        };
        guardedServices.writer = [ "/srv/protected" ];
      };
      services.openssh.enable = true;
      users.users.operator = {
        isNormalUser = true;
        openssh.authorizedKeys.keys = [ (lib.fileContents (sshFixtures + "/id_ed25519.pub")) ];
      };
      systemd.services.writer = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig.Type = "oneshot";
        script = "echo unsafe > /srv/protected/writes";
      };
      environment.systemPackages = [ pkgs.util-linux ];
    };
  };
  extraTestScript = ''
    import os, shutil, subprocess, tempfile
    machine.wait_for_unit("sshd.service")
    machine.succeed("test $(findmnt -n -o FSTYPE /) = ext4")
    machine.succeed("test ! -e /dev/mapper/original-root")
    machine.fail("test -e /srv/protected/writes")
    machine.forward_port(22445, 22)
    with tempfile.TemporaryDirectory() as directory:
        key = directory + "/operator"
        shutil.copyfile("${sshFixtures}/id_ed25519", key)
        os.chmod(key, 0o600)
        known = directory + "/known_hosts"
        with open(known, "w") as output:
            output.write("[127.0.0.1]:22445 " + machine.succeed("cat /etc/ssh/ssh_host_ed25519_key.pub"))
        result = subprocess.run(["${pkgs.openssh}/bin/ssh", "-p", "22445", "-i", key,
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + known,
            "-o", "IdentitiesOnly=yes", "operator@127.0.0.1", "id -un"],
            capture_output=True, text=True, timeout=30, check=True)
        assert result.stdout.strip() == "operator"
    machine.succeed("/run/current-system/bin/switch-to-configuration test")
    machine.fail("systemctl start writer.service")
    machine.fail("test -e /srv/protected/writes")
    machine.succeed("/run/current-system/bin/switch-to-configuration test")
    machine.shutdown()
    machine.start()
    machine.wait_for_unit("sshd.service")
    machine.fail("test -e /dev/mapper/original-root")
    machine.fail("test -e /srv/protected/writes")
  '';
}
