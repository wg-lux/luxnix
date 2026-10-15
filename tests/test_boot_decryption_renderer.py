from __future__ import annotations

from pathlib import Path
import re
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERER = (
    REPO_ROOT
    / "modules/nixos/luxnix/boot-decryption-stick/render-boot-decryption-config.sh"
)
RENDERER_MODULE = (
    REPO_ROOT
    / "modules/nixos/luxnix/boot-decryption-stick/render-boot-decryption-config.nix"
)
SETUP_MODULES = {
    "single": REPO_ROOT / "modules/nixos/luxnix/boot-decryption-stick/default.nix",
    "gs-01": REPO_ROOT
    / "modules/nixos/luxnix/boot-decryption-stick-gs-01/default.nix",
    "gs-02": REPO_ROOT
    / "modules/nixos/luxnix/boot-decryption-stick-gs-02/default.nix",
}


def _render(output: Path, *luks_devices: str) -> subprocess.CompletedProcess[str]:
    arguments = [
        "bash",
        str(RENDERER),
        "--output",
        str(output),
        "--usb-uuid",
        "12345678-1234-1234-1234-123456789abc",
        "--offset-bytes",
        "52428800",
        "--keyfile-size",
        "4096",
    ]
    for luks_device in luks_devices:
        arguments.extend(("--luks-device", luks_device))
    return subprocess.run(arguments, text=True, capture_output=True, check=False)


def test_renderer_is_shell_valid_and_only_uses_render_safe_commands() -> None:
    subprocess.run(["bash", "-n", str(RENDERER)], check=True)

    source = RENDERER.read_text(encoding="utf-8")
    assert "nixfmt \"$temporary_output\"" in source
    assert "mv \"$temporary_output\" \"$output\"" in source
    assert "mktemp --suffix=.nix" in source

    forbidden_commands = (
        "dd",
        "mkfs",
        "cryptsetup",
        "luksAddKey",
        "mount",
        "umount",
        "chown",
        "parted",
    )
    for command in forbidden_commands:
        assert not re.search(rf"(?m)^\s*{re.escape(command)}(?:\s|$)", source)


def test_renderer_writes_a_formatted_parseable_file_to_the_explicit_path(
    tmp_path: Path,
) -> None:
    output = tmp_path / "boot-decryption-config.nix"

    result = _render(output, "cryptroot0", "cryptroot1")

    assert result.returncode == 0, result.stderr
    assert output.exists()
    subprocess.run(["nixfmt", "--check", str(output)], check=True)
    subprocess.run(["nix-instantiate", "--parse", str(output)], check=True)

    rendered = output.read_text(encoding="utf-8")
    assert "boot.initrd.luks.devices = {" in rendered
    assert '"cryptroot0" = {' in rendered
    assert '"cryptroot1" = {' in rendered
    assert (
        'keyFile = "/dev/disk/by-uuid/12345678-1234-1234-1234-123456789abc";'
        in rendered
    )
    assert "keyFileOffset = 52428800;" in rendered
    assert "keyFileSize = 4096;" in rendered


def test_renderer_rejects_invalid_input_without_creating_the_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "boot-decryption-config.nix"
    result = subprocess.run(
        [
            "bash",
            str(RENDERER),
            "--output",
            str(output),
            "--usb-uuid",
            "not-a-uuid!",
            "--offset-bytes",
            "52428800",
            "--keyfile-size",
            "4096",
            "--luks-device",
            "cryptroot",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert not output.exists()


def test_all_setup_scripts_delegate_to_the_shared_renderer_after_device_setup() -> None:
    renderer_module = RENDERER_MODULE.read_text(encoding="utf-8")
    assert "pkgs.writeShellApplication" in renderer_module
    assert "pkgs.nixfmt" in renderer_module

    expected_luks_devices = {
        "single": ("cryptroot",),
        "gs-01": ("cryptroot0", "cryptroot1", "cryptroot2"),
        "gs-02": ("cryptroot0", "cryptroot1", "cryptroot2", "cryptroot3"),
    }
    for name, module_path in SETUP_MODULES.items():
        source = module_path.read_text(encoding="utf-8")
        assert "rendererPath = import" in source
        assert "rendererPath" in source.split("environment.systemPackages", 1)[1]
        assert "luxnix-render-boot-decryption-config" in source
        assert "cat <<EOF > $NIX_CONFIGURATION_OUTPUT" not in source
        assert source.index("/bin/luxnix-render-boot-decryption-config") > source.index(
            "cryptsetup luksAddKey"
        )
        for luks_device in expected_luks_devices[name]:
            assert f"--luks-device {luks_device}" in source
