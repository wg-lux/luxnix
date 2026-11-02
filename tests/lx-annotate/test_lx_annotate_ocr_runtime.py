"""Native media dependencies survive wheel deployment without a system profile link."""

import shutil
import subprocess

import pytest

from nix_eval_helpers import REPO_ROOT, eval_json


def test_report_embedding_model_reaches_web_and_workers() -> None:
    paths = eval_json("""
      let
        flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        cfg = flake.nixosConfigurations.gc-02.config;
      in map (name:
        cfg.systemd.services.${name}.environment.ENDOREG_REPORT_EMBEDDING_MODEL_PATH
      ) [
        "lx-annotate" "lx-annotate-celery-worker" "lx-annotate-celery-pipeline-worker"
      ]
    """)
    assert len(set(paths)) == 1
    assert paths[0].startswith("/nix/store/")
    assert paths[0].endswith("-de-core-news-lg-3.8.0-data")


@pytest.mark.parametrize("custom_prefix", [None, "/srv/ocr/tessdata"])
def test_gc_02_ocr_runtime_contract(custom_prefix: str | None) -> None:
    override = (
        ""
        if custom_prefix is None
        else (
            "roles.endoreg-client.lxAnnotate.runtime.tessdataPrefix = "
            '"/srv/ocr/tessdata";'
        )
    )
    result = eval_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          cfg = (flake.nixosConfigurations.gc-02.extendModules {
            modules = [({ ... }: { OVERRIDE })];
          }).config;
          runtime = cfg.services.luxnix.lxAnnotateLocal.runtime;
          contract = name: let unit = cfg.systemd.services.${name}; in {
            prefix = unit.environment.TESSDATA_PREFIX;
            path = unit.environment.PATH;
          };
        in {
          package = toString runtime.tesseractPackage;
          prefix = runtime.tessdataPrefix;
          services = map contract [
            "lx-annotate"
            "lx-annotate-celery-worker"
            "lx-annotate-celery-pipeline-worker"
          ];
        }
        """.replace("OVERRIDE", override)
    )
    expected_prefix = custom_prefix or f"{result['package']}/share/tessdata"
    assert result["prefix"] == expected_prefix
    for service in result["services"]:
        assert service["prefix"] == expected_prefix
        assert f"{result['package']}/bin" in service["path"].split(":")


def test_wheel_wrapper_provides_media_tools_without_inherited_path() -> None:
    ffmpeg_bin = eval_json("""
      let flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
      in toString (flake.nixosConfigurations.gc-10.pkgs.lib.getBin
        flake.nixosConfigurations.gc-10.pkgs.ffmpeg-headless)
    """)
    result = subprocess.run(
        [
            "nix",
            "build",
            "--no-link",
            "--print-out-paths",
            f"git+file://{REPO_ROOT}#nixosConfigurations.gc-10.config.services.lx-annotate.package",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    bash = shutil.which("bash")
    assert bash is not None
    subprocess.run(
        [
            bash,
            "-c",
            'source "$1"\n'
            '[ "$(command -v ffmpeg)" = "$2/bin/ffmpeg" ]\n'
            '[ "$(command -v ffprobe)" = "$2/bin/ffprobe" ]\n'
            "ffmpeg -version\nffprobe -version\ntesseract --version",
            "media-runtime-check",
            f"{result.stdout.strip()}/libexec/lx-annotate-wheel-runtime-lib",
            ffmpeg_bin,
        ],
        env={"PATH": ""},
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_gc_10_media_tools_execute_in_service_path() -> None:
    result = eval_json("""
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          host = flake.nixosConfigurations.gc-10;
        in {
          package = toString (host.pkgs.lib.getBin host.pkgs.ffmpeg-headless);
          services = map (name: host.config.systemd.services.${name}.environment.PATH) [
            "lx-annotate"
            "lx-annotate-celery-pipeline-worker"
            "lx-annotate-celery-ffmpeg-worker"
          ];
        }
        """)
    subprocess.run(
        [
            "nix",
            "build",
            "--no-link",
            f"git+file://{REPO_ROOT}#nixosConfigurations.gc-10.pkgs.ffmpeg-headless",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    for service_path in result["services"]:
        assert f"{result['package']}/bin" in service_path.split(":")
        for executable in ("ffmpeg", "ffprobe"):
            subprocess.run(
                [executable, "-version"],
                env={"PATH": service_path},
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
    encoders = subprocess.run(
        [f"{result['package']}/bin/ffmpeg", "-hide_banner", "-encoders"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    names = {
        line.split()[1]
        for line in encoders.stdout.splitlines()
        if len(line.split()) > 1
    }
    assert {"libx264", "h264_nvenc"} <= names


def test_gc_02_tesseract_package_contains_required_languages() -> None:
    result = subprocess.run(
        [
            "nix",
            "build",
            "--no-link",
            "--print-out-paths",
            f"git+file://{REPO_ROOT}#nixosConfigurations.gc-02.config."
            "services.luxnix.lxAnnotateLocal.runtime.tesseractPackage",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    package = result.stdout.strip()
    languages = subprocess.run(
        [
            f"{package}/bin/tesseract",
            "--tessdata-dir",
            f"{package}/share/tessdata",
            "--list-langs",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert {"deu", "eng"} <= set(languages.stdout.splitlines())


@pytest.mark.parametrize("host_name", ["gc-02", "gc-10"])
def test_libmagic_classifies_pdf_in_web_and_worker_runtime(host_name: str) -> None:
    result = eval_json(
        """
        let
          flake = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          host = flake.nixosConfigurations.HOST_NAME;
        in {
          library = toString (host.pkgs.lib.getLib host.pkgs.file);
          python = "${host.pkgs.python312}/bin/python";
          services = map (name:
            host.config.systemd.services.${name}.environment.LD_LIBRARY_PATH
          ) [
            "lx-annotate"
            "lx-annotate-celery-worker"
            "lx-annotate-celery-pipeline-worker"
          ];
        }
        """.replace("HOST_NAME", host_name)
    )
    subprocess.run(
        [
            "nix",
            "build",
            "--no-link",
            f"git+file://{REPO_ROOT}#nixosConfigurations.{host_name}.pkgs.file",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    for library_path in result["services"]:
        assert f"{result['library']}/lib" in library_path.split(":")
        subprocess.run(
            [
                result["python"],
                "-I",
                "-S",
                "-c",
                r"""
import ctypes
library = ctypes.CDLL("libmagic.so.1")
library.magic_open.restype = ctypes.c_void_p
library.magic_load.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
library.magic_buffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
library.magic_buffer.restype = ctypes.c_char_p
library.magic_close.argtypes = [ctypes.c_void_p]
cookie = library.magic_open(0x10)
assert cookie
try:
    assert library.magic_load(cookie, None) == 0
    content = b"%PDF-1.4\n%%EOF\n"
    assert library.magic_buffer(cookie, content, len(content)) == b"application/pdf"
finally:
    library.magic_close(cookie)
                """,
            ],
            env={"LD_LIBRARY_PATH": library_path},
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
