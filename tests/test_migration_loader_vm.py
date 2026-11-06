"""Opt-in real initrd boot test; no host mounts, disks, secrets or firmware writes.

Set LUXNIX_MIGRATION_BUNDLE to a disposable test-host bundle and LUXNIX_QEMU
to qemu-system-x86_64. This tests the loader, not the UEFI signature chain.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("LUXNIX_MIGRATION_BUNDLE") or not os.environ.get("LUXNIX_QEMU"),
    reason="requires an explicitly built disposable bundle and QEMU",
)


def test_signed_loader_rejects_modified_payload_manifest(tmp_path):
    bundle = Path(os.environ["LUXNIX_MIGRATION_BUNDLE"])
    assert json.loads((bundle / "manifest.json").read_text())["host"] == "test-host"
    key, certificate = tmp_path / "test.key", tmp_path / "test.pem"
    signed = tmp_path / "signed.efi"

    def run(*args):
        return subprocess.run(list(map(str, args)), check=True, capture_output=True)

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
    if case == "decline" and not local_console:
        pytest.skip("console refusal requires local-console fixture")
    assert spec["recovery"] == {
        "uuid": "1111-2222",
        "fstype": "vfat",
        "luks_uuid": None,
    }
    for tool in ("mkfs.vfat", "mcopy", "mmd", "objcopy"):
        assert shutil.which(tool), f"Required test tool missing: {tool}"

    def run(*args):
        subprocess.run(list(map(str, args)), check=True, capture_output=True)

    for section in ("linux", "initrd", "cmdline"):
        run(
            "objcopy",
            "--only-section=." + section,
            "-O",
            "binary",
            bundle / "migration.efi",
            tmp_path / section,
        )
    disk = tmp_path / "recovery.img"
    with disk.open("wb") as stream:
        stream.truncate(768 * 1024**2)
    run("mkfs.vfat", "-F", "32", "-i", "11112222", disk)
    run("mmd", "-i", disk, "::/luxnix-migration")
    payload = bundle / "migration.squashfs"
    if tamper:
        payload = tmp_path / "corrupt.squashfs"
        shutil.copyfile(bundle / "migration.squashfs", payload)
        with payload.open("r+b") as stream:
            stream.write(b"bad!")
    run(
        "mcopy",
        "-i",
        disk,
        payload,
        "::/luxnix-migration/" + spec["payload"]["sha256"] + ".squashfs",
    )
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
        "-device",
        "ide-hd,drive=recovery,serial=test-recovery-disk",
    ]
    with (tmp_path / "qemu.log").open("w") as log, serial.open("w") as output_log:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=output_log, stderr=log
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
                        process.stdin.write(
                            b"test $(id -u) = 0 "
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


if __name__ == "__main__":
    # Reuse the test specification, including the canonical YAML policy.
    # This deliberately builds an unsigned disposable image, never a release.
    from tests.test_migration_boot import spec as specification

    root = Path(__file__).resolve().parents[1]
    fixture = specification.__wrapped__()
    if os.environ.get("LUXNIX_MIGRATION_LOCAL_CONSOLE"):
        fixture.update(boot_trust="local-console", console="ttyS0")
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
