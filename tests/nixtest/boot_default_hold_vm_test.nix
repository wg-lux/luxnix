# Real UEFI firmware and systemd-boot: while the root is between conversion and
# installation, a power cut must start the migration environment again, and the
# install hand-over must make the normal generation boot afterwards. Disposable
# VM only; no disk is converted here (boot-storage-in-place covers conversion).
{ pkgs, repoRoot }:
let
  driver = pkgs.writeText "boot-default-driver.py" ''
    import sys
    from pathlib import Path

    sys.path.insert(0, "${repoRoot}")
    from lx_administration.storage import migration_boot as boot

    command = sys.argv[1]
    if command == "hold":
        print(boot.hold_for_migration("machine"))
    elif command == "release":
        boot.release_hold({"held": True, "previous": sys.argv[2] if len(sys.argv) > 2 else None})
    elif command == "hand-over":
        print(boot.hand_over_boot(Path("/"), Path("/boot"), sys.argv[2]))
    else:
        print(boot.loader_variable(command))
  '';
in
pkgs.testers.runNixOSTest {
  name = "boot-default-hold";
  nodes.machine =
    { pkgs, ... }:
    {
      virtualisation = {
        useBootLoader = true;
        useEFIBoot = true;
      };
      boot.loader = {
        systemd-boot.enable = true;
        efi.canTouchEfiVariables = true;
      };
      environment.systemPackages = [ pkgs.python3 ];
      # A bootloader VM sees only the system closure; this pulls the driver in.
      environment.etc."boot-default-driver.py".source = driver;
    };
  testScript = ''
    run = "python3 /etc/boot-default-driver.py "

    def selected():
        return machine.succeed(run + "LoaderEntrySelected").strip()

    def boot_again(crash=False):
        if crash:
            machine.crash()
        else:
            machine.shutdown()
        machine.start()
        machine.wait_for_unit("multi-user.target")

    machine.wait_for_unit("multi-user.target")
    closure = machine.succeed("readlink -f /run/current-system").strip()
    normal = selected()
    assert normal.startswith("nixos-generation-"), normal
    generation = normal.removeprefix("nixos-generation-").removesuffix(".conf")
    # The hand-over reads the installed profile, as nixos-install leaves it.
    machine.succeed(
        "test -e /nix/var/nix/profiles/system || { mkdir -p /nix/var/nix/profiles; "
        f"ln -s {closure} /nix/var/nix/profiles/system-{generation}-link; "
        f"ln -s system-{generation}-link /nix/var/nix/profiles/system; }}"
    )
    machine.succeed(f"grep -x 'default {normal}' /boot/loader/loader.conf")

    # Stage a migration entry as migration-boot does: present, never the default.
    migration = "luxnix-migration-machine-0123456789abcdef.conf"
    machine.succeed(f"cp /boot/loader/entries/{normal} /boot/loader/entries/{migration}")
    machine.succeed(f"bootctl set-oneshot {migration}")
    boot_again()
    assert selected() == migration, "the one-shot did not start the migration entry"

    with subtest("Holding survives power cuts until the hand-over"):
        assert "'held': True" in machine.succeed(run + "hold")
        assert machine.succeed(run + "LoaderEntryDefault").strip() == migration
        # Power cut after conversion, before installation: back to migration.
        boot_again(crash=True)
        assert selected() == migration, "a power cut started the old system"
        boot_again(crash=True)
        assert selected() == migration

    with subtest("Releasing an unneeded hold returns to the normal default"):
        machine.succeed(run + "release")
        assert machine.succeed(run + "LoaderEntryDefault").strip() == "None"
        boot_again()
        assert selected() == normal
        machine.succeed(f"bootctl set-oneshot {migration}")
        boot_again()
        assert selected() == migration
        assert "'held': True" in machine.succeed(run + "hold")

    with subtest("The hand-over clears every override and boots the installed system"):
        machine.succeed(f"bootctl set-oneshot {migration}")
        assert machine.succeed(run + "hand-over " + closure).strip() == normal
        assert machine.succeed(run + "LoaderEntryDefault").strip() == "None"
        assert machine.succeed(run + "LoaderEntryOneShot").strip() == "None"
        boot_again()
        assert selected() == normal, "the installed generation did not boot"
        boot_again(crash=True)
        assert selected() == normal

    with subtest("A hold is refused from outside the migration entry"):
        assert "'held': False" in machine.succeed(run + "hold")
        assert machine.succeed(run + "LoaderEntryDefault").strip() == "None"
  '';
}
