"""Controller signing and host import with the real lzbt, sbctl and sbverify."""

import io
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from lx_administration import secure_boot

ROOT = Path(__file__).resolve().parents[1]
MINIMAL_SYSTEM = r"""
  let
    f = builtins.getFlake ("git+file://" + toString ./.);
    system = f.inputs.nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [ f.inputs.lanzaboote.nixosModules.lanzaboote {
        system.stateVersion = "26.05";
        fileSystems."/" = { device = "/dev/vda"; fsType = "ext4"; };
        documentation.enable = false;
        boot.loader.systemd-boot.enable = false;
        boot.lanzaboote = { enable = true; pkiBundle = "/var/empty"; };
      } ];
    };
    c = system.config;
  in { inherit (c.boot.lanzaboote) installCommand; systemd = c.systemd.package.outPath;
       toplevel = c.system.build.toplevel.outPath; }
"""


def _nix(*args):
    return subprocess.run(
        ["nix", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=1800,
    ).stdout.strip()


@pytest.fixture(scope="module")
def system(tmp_path_factory):
    if shutil.which("nix") is None:
        pytest.skip("Nix required")
    tools = [
        _nix(
            "build",
            "--no-link",
            "--print-out-paths",
            "--inputs-from",
            ".",
            f"nixpkgs#{p}",
        )
        for p in ("sbctl", "sbsigntool")
    ]
    os.environ["PATH"] = ":".join(f"{t}/bin" for t in tools) + ":" + os.environ["PATH"]
    expression = MINIMAL_SYSTEM
    _nix("build", "--impure", "--no-link", "--expr", f"({expression}).toplevel")
    # Realise lzbt, systemd-boot and loader.conf referenced by the install command.
    _nix(
        "build",
        "--impure",
        "--no-link",
        "--expr",
        '(builtins.getFlake ("git+file://" + toString ./.))'
        ".inputs.nixpkgs.legacyPackages.x86_64-linux.writeText"
        f' "install" ({expression}).installCommand',
    )
    values = {
        key: _nix("eval", "--impure", "--raw", "--expr", f"({expression}).{key}")
        for key in ("installCommand", "systemd", "toplevel")
    }
    return values, tmp_path_factory


def _keys(directory):
    directory.mkdir()
    config = directory / "sbctl.conf"
    config.write_text(f"keydir: {directory}/keys\nguid: {directory}/GUID\n")
    subprocess.run(
        ["sbctl", "--quiet", "--config", str(config), "create-keys"],
        check=True,
        capture_output=True,
    )
    return directory / "keys"


def _stage(system, keys, generation=7):
    values, factory = system
    esp = factory.mktemp("controller") / "esp"
    esp.mkdir()
    files = secure_boot.stage_artifacts(
        install_command=values["installCommand"],
        systemd=values["systemd"],
        toplevel=Path(values["toplevel"]),
        generation=generation,
        keys=keys,
        esp=esp,
    )
    archive = esp.parent / "artifacts.tar"
    with tarfile.open(archive, "w") as tar:
        for name in files:
            tar.add(esp / name, arcname=name)
    return files, archive


def _host_install(system, esp, certificate, generation=7):
    values, factory = system
    profiles = factory.mktemp("profiles")
    (profiles / f"system-{generation}-link").symlink_to(values["toplevel"])
    command = (
        f"{values['installCommand']} --public-key={certificate}"
        f" --private-key=/nonexistent/no-private-key-on-host {esp} {profiles}/system-*-link"
    )
    env = {
        **os.environ,
        "PATH": f"{values['systemd']}/lib/systemd:{os.environ['PATH']}",
    }
    return subprocess.run(
        ["bash", "-c", command], env=env, capture_output=True, text=True
    )


def test_controller_signs_and_keyless_host_install_registers(system, tmp_path):
    keys = _keys(tmp_path / "pki")
    files, archive = _stage(system, keys)
    assert any(name.startswith("EFI/Linux/nixos-generation-7-") for name in files)
    assert {"EFI/systemd/systemd-bootx64.efi", "EFI/BOOT/BOOTX64.EFI"} <= set(files)
    host_esp = tmp_path / "host-esp"
    host_esp.mkdir()
    certificate = tmp_path / "db.pem"
    shutil.copyfile(keys / "db/db.pem", certificate)
    assert sorted(secure_boot.import_artifacts(archive, host_esp, certificate)) == files
    # Re-import is idempotent.
    assert secure_boot.import_artifacts(archive, host_esp, certificate) == []
    result = _host_install(system, host_esp, certificate)
    assert result.returncode == 0, result.stderr
    for name in files:
        if secure_boot.SIGNED.match(name):
            subprocess.run(
                ["sbverify", "--cert", str(certificate), str(host_esp / name)],
                check=True,
                capture_output=True,
            )


def test_keyless_host_install_fails_for_unsigned_generation(system, tmp_path):
    keys = _keys(tmp_path / "pki")
    host_esp = tmp_path / "host-esp"
    host_esp.mkdir()
    result = _host_install(system, host_esp, keys / "db/db.pem")
    assert result.returncode != 0
    assert not list(host_esp.rglob("nixos-generation-*.efi"))


def test_import_rejects_foreign_signature_and_unsafe_archives(system, tmp_path):
    _, archive = _stage(system, _keys(tmp_path / "signer"))
    other = _keys(tmp_path / "other")
    esp = tmp_path / "esp"
    esp.mkdir()
    with pytest.raises(secure_boot.SecureBootError):
        secure_boot.import_artifacts(archive, esp, other / "db/db.pem")
    assert not any(p.is_file() for p in esp.rglob("*"))
    for name in ("../escape.efi", "EFI/Linux/other.efi", "loader/loader.conf"):
        unsafe = tmp_path / "unsafe.tar"
        with tarfile.open(unsafe, "w") as tar:
            info = tarfile.TarInfo(name)
            info.size = 1
            tar.addfile(info, io.BytesIO(b"x"))
        with pytest.raises(
            secure_boot.SecureBootError, match="Unexpected boot artifact"
        ):
            secure_boot.import_artifacts(unsafe, esp, other / "db/db.pem")


def test_import_never_replaces_differing_immutable_artifact(system, tmp_path):
    keys = _keys(tmp_path / "pki")
    files, archive = _stage(system, keys)
    esp = tmp_path / "esp"
    stub = next(name for name in files if name.startswith("EFI/Linux/"))
    (esp / stub).parent.mkdir(parents=True)
    (esp / stub).write_bytes(b"different")
    with pytest.raises(secure_boot.SecureBootError, match="Refusing to replace"):
        secure_boot.import_artifacts(archive, esp, keys / "db/db.pem")
    assert (esp / stub).read_bytes() == b"different"
