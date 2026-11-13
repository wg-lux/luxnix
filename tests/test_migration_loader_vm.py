"""Opt-in real initrd boot test; no host mounts, disks, secrets or firmware writes.

Set LUXNIX_MIGRATION_BUNDLE to a disposable test-host bundle and LUXNIX_QEMU
to qemu-system-x86_64. OVMF_CODE/VARS enable the complete UEFI/physical-console
test. This does not establish firmware trust or physical-host acceptance.
"""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("LUXNIX_MIGRATION_BUNDLE") or not os.environ.get("LUXNIX_QEMU"),
    reason="requires an explicitly built disposable bundle and QEMU",
)


def run(*args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True)


# Real recovery media are USB SSDs and NVMe enclosures, which attach through UAS.
USB_RECOVERY = [
    "-device", "qemu-xhci,id=xhci",
    "-device", "usb-uas,id=uas,bus=xhci.0",
    "-device", "scsi-hd,bus=uas.0,scsi-id=0,lun=0,drive=recovery,"
    "serial=test-recovery-disk",
]  # fmt: skip


def qemu_environment():
    # The Python shell's libraries can use a different glibc from pinned QEMU.
    return {key: value for key, value in os.environ.items() if key != "LD_LIBRARY_PATH"}


def recovery_disk(bundle, spec, directory, *, tamper=False):
    """An ext4 image with the signed filesystem UUID, built without root."""
    disk = directory / "recovery.img"
    content = directory / "recovery"
    (content / "luxnix-migration").mkdir(parents=True)
    payload = content / "luxnix-migration" / (spec["payload"]["sha256"] + ".squashfs")
    shutil.copyfile(bundle / "migration.squashfs", payload)
    if tamper:
        with payload.open("r+b") as stream:
            stream.write(b"bad!")
    with disk.open("wb") as stream:
        stream.truncate(768 * 1024**2)
    run("mkfs.ext4", "-q", "-U", spec["recovery"]["uuid"], "-d", content, disk)
    shutil.rmtree(content)
    return disk


def test_signed_loader_rejects_modified_payload_manifest(tmp_path):
    bundle = Path(os.environ["LUXNIX_MIGRATION_BUNDLE"])
    assert json.loads((bundle / "manifest.json").read_text())["host"] == "test-host"
    key, certificate = tmp_path / "test.key", tmp_path / "test.pem"
    signed = tmp_path / "signed.efi"

    run(
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=LuxNix disposable loader test",
        "-keyout",
        key,
        "-out",
        certificate,
    )
    run(
        "sbsign",
        "--key",
        key,
        "--cert",
        certificate,
        "--output",
        signed,
        bundle / "migration.efi",
    )
    run("sbverify", "--cert", certificate, signed)
    content = signed.read_bytes()
    marker = b"ID=luxnix-migration"
    assert content.count(marker) == 1
    signed.write_bytes(content.replace(marker, b"ID=luxnix-migratiom"))
    result = subprocess.run(
        ["sbverify", "--cert", str(certificate), str(signed)], capture_output=True
    )
    assert result.returncode != 0


@pytest.mark.parametrize("case", ["accept", "decline", "tamper"])
def test_split_loader_boots_only_authenticated_ram_payload(tmp_path, case):
    tamper = case == "tamper"
    bundle = Path(os.environ["LUXNIX_MIGRATION_BUNDLE"])
    spec = json.loads((bundle / "manifest.json").read_text())
    assert spec["host"] == "test-host"
    local_console = spec.get("boot_trust") == "local-console"
    if local_console and spec.get("console") == "tty1":
        pytest.skip("physical-console fixture is exercised through UEFI below")
    if case == "decline" and not local_console:
        pytest.skip("console refusal requires local-console fixture")
    assert spec["recovery"]["fstype"] == "ext4" and not spec["recovery"]["luks_uuid"]
    for tool in ("mkfs.ext4", "objcopy"):
        assert shutil.which(tool), f"Required test tool missing: {tool}"

    for section in ("linux", "initrd", "cmdline"):
        run(
            "objcopy",
            "--only-section=." + section,
            "-O",
            "binary",
            bundle / "migration.efi",
            tmp_path / section,
        )
    disk = recovery_disk(bundle, spec, tmp_path, tamper=tamper)
    cmdline = (tmp_path / "cmdline").read_bytes().rstrip(b"\0").decode()
    for argument in ("noresume", "rd.systemd.gpt_auto=0", "systemd.gpt_auto=0"):
        assert argument in cmdline.split()
    cmdline += " systemd.show_status=1 systemd.log_level=info"
    serial = tmp_path / "serial.log"
    command = [
        os.environ["LUXNIX_QEMU"],
        "-enable-kvm",
        "-machine",
        "q35",
        "-m",
        "6144",
        "-smp",
        "2",
        "-nodefaults",
        "-display",
        "none",
        "-serial",
        "stdio",
        "-monitor",
        "none",
        "-no-reboot",
        "-uuid",
        spec["hardware_uuid"],
        "-kernel",
        str(tmp_path / "linux"),
        "-initrd",
        str(tmp_path / "initrd"),
        "-append",
        cmdline,
        "-drive",
        f"file={disk},format=raw,if=none,id=recovery",
        *USB_RECOVERY,
    ]
    with (tmp_path / "qemu.log").open("w") as log, serial.open("w") as output_log:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=output_log, stderr=log,
            env=qemu_environment(),
        )
        try:
            deadline = time.monotonic() + 120
            marker = (
                "Migration payload admission failed" if tamper else "Multi-User System"
            )
            if local_console and not tamper:
                marker = (
                    "Local console approval declined"
                    if case == "decline"
                    else "LUXNIX_CONSOLE_READY"
                )
            confirmed = False
            probed = False
            while time.monotonic() < deadline:
                output = serial.read_text(errors="replace") if serial.exists() else ""
                if local_console and not tamper:
                    if "to open migration access:" in output and not confirmed:
                        assert "RAM environment admitted" not in output
                        phrase = (
                            f"BOOT UNVERIFIED {spec['host']} {spec['revision'][:12]}"
                        )
                        process.stdin.write(
                            ((phrase if case == "accept" else "no") + "\n").encode()
                        )
                        process.stdin.flush()
                        confirmed = True
                    if ":/]#" in output and confirmed and not probed:
                        ssh_check = (
                            b'test -z "$(systemctl show sshd.service '
                            b'-p FragmentPath --value)" && '
                            if not spec["authorized_keys"]
                            else b""
                        )
                        process.stdin.write(
                            ssh_check + b"test $(id -u) = 0 "
                            b"&& test $(findmnt -n -o FSTYPE /) = tmpfs "
                            b'&& test -z "$(swapon --show --noheadings)" '
                            b"&& printf 'LUXNIX_%s\\n' CONSOLE_READY\n"
                        )
                        process.stdin.flush()
                        probed = True
                if marker in output:
                    break
                if not tamper and "Migration payload admission failed" in output:
                    pytest.fail(f"Loader refused valid payload; see {serial}")
                if "Freezing execution" in output or "Emergency Mode" in output:
                    pytest.fail(f"Guest startup failed; see {serial}")
                if process.poll() is not None:
                    pytest.fail(f"QEMU exited; see {tmp_path}")
                time.sleep(0.5)
            else:
                pytest.fail(f"Boot marker missing; see {serial}")
            if tamper:
                assert "Multi-User System" not in output
                assert "nix-store.squashfs.partial: FAILED" in output
            else:
                assert (
                    "Migration payload authenticated in RAM; recovery source detached."
                    in output
                )
        finally:
            process.terminate()
            process.wait(timeout=15)


def test_uefi_physical_console_boots_in_five_gib(tmp_path):
    """Boot the actual EFI file, then use VGA keyboard input to reach a RAM shell."""
    bundle = Path(os.environ["LUXNIX_MIGRATION_BUNDLE"])
    spec = json.loads((bundle / "manifest.json").read_text())
    if spec.get("console") != "tty1" or spec.get("boot_trust") != "local-console":
        pytest.skip("requires the local-console tty1 fixture")
    firmware = [os.environ.get("OVMF_CODE"), os.environ.get("OVMF_VARS")]
    if not all(firmware):
        pytest.skip("requires disposable OVMF firmware")
    assert spec["host"] == "test-host" and spec["authorized_keys"] == []
    for tool in ("mkfs.vfat", "mkfs.ext4", "mcopy", "mmd", "sfdisk", "objcopy"):
        assert shutil.which(tool), f"Required test tool missing: {tool}"

    cmdline = tmp_path / "cmdline"
    run(
        "objcopy",
        "--only-section=.cmdline",
        "-O",
        "binary",
        bundle / "migration.efi",
        cmdline,
    )
    arguments = cmdline.read_bytes().rstrip(b"\0").decode().split()
    assert [a for a in arguments if a.startswith("console=")][-1] == "console=tty1"
    assert "nomodeset" in arguments and "quiet" not in arguments
    assert {"loglevel=7", "rd.systemd.show_status=1", "systemd.show_status=1"} <= set(
        arguments
    )

    esp = tmp_path / "esp.img"
    with esp.open("wb") as stream:
        stream.truncate(256 * 1024**2)
    subprocess.run(
        ["sfdisk", str(esp)],
        input="label: gpt\nstart=2048,size=262144,type=U\n",
        text=True,
        capture_output=True,
        check=True,
    )
    run("mkfs.vfat", "-F", "32", "--offset=2048", esp, "131072")
    filesystem = str(esp) + "@@1048576"
    run("mmd", "-i", filesystem, "::/EFI", "::/EFI/BOOT")
    run("mcopy", "-i", filesystem, bundle / "migration.efi", "::/EFI/BOOT/BOOTX64.EFI")
    disk = recovery_disk(bundle, spec, tmp_path)
    variables = tmp_path / "vars.fd"
    shutil.copyfile(firmware[1], variables)
    serial = tmp_path / "serial.log"
    monitor = tmp_path / "monitor.sock"
    runtime = spec["hardware_uuid"]
    command = [
        os.environ["LUXNIX_QEMU"],
        "-enable-kvm",
        "-cpu",
        "host",
        "-machine",
        "q35",
        "-m",
        "5120",
        "-smp",
        "2",
        "-nodefaults",
        "-device",
        "virtio-vga",
        "-display",
        "none",
        "-serial",
        f"file:{serial}",
        "-monitor",
        f"unix:{monitor},server=on,wait=off",
        "-no-reboot",
        "-uuid",
        runtime,
        "-drive",
        f"if=pflash,format=raw,readonly=on,file={firmware[0]}",
        "-drive",
        f"if=pflash,format=raw,file={variables}",
        "-drive",
        f"file={esp},format=raw,if=none,id=esp",
        "-device",
        "virtio-blk-pci,drive=esp,serial=test-esp,bootindex=1",
        "-drive",
        f"file={disk},format=raw,if=none,id=recovery",
        *USB_RECOVERY,
    ]

    def request(connection, text):
        connection.sendall((text + "\n").encode())
        response = b""
        while b"(qemu)" not in response:
            chunk = connection.recv(65536)
            assert chunk, "QEMU monitor closed"
            response += chunk
        assert b"unknown" not in response.lower(), response

    def type_keys(connection, text):
        # QEMU keys are US positions; the RAM environment reads them with the
        # fleet's German layout, where these characters sit on other keys.
        special = {
            " ": "spc",
            "-": "slash",
            "/": "shift-7",
            ">": "shift-less",
            "\n": "ret",
        }
        swapped = str.maketrans("yzYZ", "zyZY")
        for character in text:
            position = character.translate(swapped)
            key = special.get(
                character,
                "shift-" + position.lower() if position.isupper() else position,
            )
            request(connection, "sendkey " + key + " 1")
            time.sleep(0.01)

    with (tmp_path / "qemu.log").open("w") as log:
        process = subprocess.Popen(
            command, stdout=log, stderr=log, env=qemu_environment()
        )
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(30)
                deadline = time.monotonic() + 10
                while not monitor.exists() and time.monotonic() < deadline:
                    assert process.poll() is None, f"QEMU exited; see {tmp_path}"
                    time.sleep(0.1)
                connection.connect(str(monitor))
                response = b""
                while b"(qemu)" not in response:
                    response += connection.recv(65536)
                # Connect before firmware starts. A framebuffer boot can delay
                # accepting a new monitor client while the display is busy.
                ready = time.monotonic() + 90
                while time.monotonic() < ready:
                    assert process.poll() is None, f"QEMU exited; see {tmp_path}"
                    time.sleep(0.5)
                request(connection, f'screendump "{tmp_path / "approval.ppm"}"')
                type_keys(
                    connection, f"BOOT UNVERIFIED test-host {spec['revision'][:12]}\n"
                )
                time.sleep(3)
                type_keys(
                    connection,
                    "echo LUXNIX-UEFI-CHECK-BEGIN > /dev/ttyS0\n"
                    "id -u > /dev/ttyS0\n"
                    "findmnt -n -o FSTYPE / > /dev/ttyS0\n"
                    "swapon --show --noheadings > /dev/ttyS0\n"
                    "echo LUXNIX-UEFI-CHECK-END > /dev/ttyS0\n",
                )
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    output = serial.read_text(errors="replace")
                    if "LUXNIX-UEFI-CHECK-END" in output:
                        break
                    assert process.poll() is None, f"QEMU exited; see {tmp_path}"
                    time.sleep(0.5)
                else:
                    pytest.fail(
                        f"Physical-console RAM shell unavailable; see {tmp_path}"
                    )
                result = output.split("LUXNIX-UEFI-CHECK-BEGIN", 1)[1].split(
                    "LUXNIX-UEFI-CHECK-END", 1
                )[0]
                assert result.split() == ["0", "tmpfs"]
                request(connection, f'screendump "{tmp_path / "shell.ppm"}"')
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


if __name__ == "__main__":
    # Reuse the test specification, including the canonical YAML policy.
    # This deliberately builds an unsigned disposable image, never a release.
    from tests.test_migration_boot import spec as specification

    root = Path(__file__).resolve().parents[1]
    fixture = specification.__wrapped__()
    if os.environ.get("LUXNIX_MIGRATION_LOCAL_CONSOLE"):
        fixture.update(
            boot_trust="local-console",
            console=os.environ.get("LUXNIX_MIGRATION_CONSOLE", "ttyS0"),
            authorized_keys=[],
        )
    serialized = json.dumps(json.dumps(fixture))
    module = json.dumps(str(root / "conf/migration-environment.nix"))
    expression = (
        f"let f = builtins.getFlake {json.dumps('git+file://' + str(root))}; "
        f"in (import (builtins.toPath {module}) {{ inputs = f.inputs; "
        f"spec = builtins.fromJSON {serialized}; "
        "}).config.system.build.migrationBundle"
    )
    subprocess.run(
        [
            "nix",
            "build",
            "--impure",
            "--no-link",
            "--print-out-paths",
            "--expr",
            expression,
        ],
        check=True,
    )
