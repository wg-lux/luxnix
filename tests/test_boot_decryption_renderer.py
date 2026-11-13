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
        "--key-partuuid",
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
        'keyFile = "/dev/disk/by-partuuid/12345678-1234-1234-1234-123456789abc";'
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
            "--key-partuuid",
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

    for module_path in SETUP_MODULES.values():
        source = module_path.read_text(encoding="utf-8")
        assert 'import ' in source and 'module.nix' in source
        assert 'mappings' not in source
    shared = (SETUP_MODULES['single'].parent / 'module.nix').read_text()
    assert '--block-size ${toString cfg.bs} --count ${toString cfg.count}' in shared
    assert 'setup.py' in shared
    assert 'config.boot.initrd.luks.devices' in shared


def test_legacy_filesystem_uuid_contract_is_rejected(tmp_path):
    result = subprocess.run(['bash', str(RENDERER), '--output', str(tmp_path / 'config.nix'),
        '--usb-uuid', '12345678-1234-1234-1234-123456789abc', '--offset-bytes', '52428800',
        '--keyfile-size', '4096', '--luks-device', 'cryptroot'], capture_output=True, text=True)
    assert result.returncode == 2
    assert not (tmp_path / 'config.nix').exists()


def test_reserved_partition_allows_zero_offset(tmp_path):
    output = tmp_path / 'config.nix'
    result = subprocess.run(['bash', str(RENDERER), '--output', str(output),
        '--key-partuuid', '12345678-1234-1234-1234-123456789abc', '--offset-bytes', '0',
        '--keyfile-size', '8192', '--luks-device', 'cryptroot'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    source = output.read_text()
    assert 'keyFileOffset = 0;' in source and 'keyFileSize = 8192;' in source
