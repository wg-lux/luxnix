from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path("/home/admin/luxnix")
SCRIPTS_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "scripts.nix"
)


def _extract_function(function_name: str) -> str:
    source = SCRIPTS_NIX.read_text(encoding="utf-8")
    match = re.search(
        rf"{function_name}\(\) \{{\n(.*?)\n    \}}",
        source,
        flags=re.DOTALL,
    )
    assert match is not None, f"Could not locate {function_name} in scripts.nix"
    body = textwrap.dedent(match.group(1))
    body = re.sub(r"\$\{pkgs\.[^}]+\}/bin/([A-Za-z0-9_.+-]+)", r"\1", body)
    body = body.replace(
        'local wheelhouse_path="${optionalString (cfg.runtime.wheelhousePath != null) (toString cfg.runtime.wheelhousePath)}"',
        'local wheelhouse_path="${WHEELHOUSE_PATH:-}"',
    )
    body = body.replace("''${", "${")
    return f"{function_name}() {{\n{body}\n}}"


def _make_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_ensure_wheel_runtime_installed_mocks_venv_creation(tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    env_conf_dir = tmp_path / "conf"
    env_data_dir = tmp_path / "data"
    runtime_static_root = tmp_path / "static"
    wheel_file = tmp_path / "0123456789abcdef0123456789abcdef-lx_annotate-0.0.3-py3-none-any.whl"
    wheel_file.write_bytes(b"fake-wheel")
    calls_log = tmp_path / "calls.log"
    fake_python = tmp_path / "fake-python"

    _make_executable(
        fake_python,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'python:%s\\n' "$*" >> "{calls_log}"
            if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then
              target="$3"
              mkdir -p "$target/bin"
              cat > "$target/bin/python" <<'EOF'
            #!/usr/bin/env bash
            exit 0
            EOF
              chmod +x "$target/bin/python"
              cat > "$target/bin/pip" <<'EOF'
            #!/usr/bin/env bash
            printf 'pip:%s\\n' "$*" >> "{calls_log}"
            exit 0
            EOF
              chmod +x "$target/bin/pip"
              exit 0
            fi
            exit 1
            """
        ),
    )

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        log() {{ :; }}
        warn() {{ :; }}
        die() {{
          printf '%s\\n' "$*" >&2
          exit 1
        }}
        {_extract_function("ensure_wheel_runtime_installed")}
        ensure_wheel_runtime_installed
        printf 'venv=%s\\n' "$LX_ANNOTATE_WHEEL_VENV"
        printf 'app_root=%s\\n' "$LX_ANNOTATE_WHEEL_APP_ROOT"
        printf 'hash=%s\\n' "$WHEEL_INSTALL_HASH"
        """
    )

    env = os.environ.copy()
    env.update(
        {
            "runtimeRootPath": str(runtime_root),
            "runtimeWheelRootPath": str(runtime_wheel_root),
            "runtimeWheelVenvPath": str(runtime_venv),
            "envConfDir": str(env_conf_dir),
            "envDataDir": str(env_data_dir),
            "runtimeStaticRootPath": str(runtime_static_root),
            "wheelFilePath": str(wheel_file),
            "pythonInterpreter": str(fake_python),
            "PATH": os.environ["PATH"],
        }
    )

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert runtime_venv.joinpath("bin", "python").exists()
    assert runtime_venv.joinpath("bin", "pip").exists()
    assert calls_log.read_text(encoding="utf-8").splitlines() == [
        f"python:-m venv {runtime_venv}",
        f"pip:install --upgrade --force-reinstall {runtime_root / 'lx_annotate-0.0.3-py3-none-any.whl'}",
    ]
    assert f"venv={runtime_venv}" in result.stdout
    assert f"app_root={runtime_wheel_root}" in result.stdout
    assert "hash=" in result.stdout


def test_ensure_wheel_runtime_installed_skips_venv_creation_when_python_exists(
    tmp_path: Path,
):
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    env_conf_dir = tmp_path / "conf"
    env_data_dir = tmp_path / "data"
    runtime_static_root = tmp_path / "static"
    wheel_file = tmp_path / "0123456789abcdef0123456789abcdef-lx_annotate-0.0.3-py3-none-any.whl"
    wheel_file.write_bytes(b"fake-wheel")
    calls_log = tmp_path / "calls.log"
    fake_python = tmp_path / "fake-python"
    existing_python = runtime_venv / "bin" / "python"
    existing_pip = runtime_venv / "bin" / "pip"
    existing_python.parent.mkdir(parents=True, exist_ok=True)
    _make_executable(existing_python, "#!/usr/bin/env bash\nexit 0\n")
    _make_executable(
        existing_pip,
        f"#!/usr/bin/env bash\nprintf 'pip:%s\\n' \"$*\" >> \"{calls_log}\"\nexit 0\n",
    )
    _make_executable(
        fake_python,
        f"#!/usr/bin/env bash\nprintf 'python:%s\\n' \"$*\" >> \"{calls_log}\"\nexit 1\n",
    )

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        log() {{ :; }}
        warn() {{ :; }}
        die() {{
          printf '%s\\n' "$*" >&2
          exit 1
        }}
        {_extract_function("ensure_wheel_runtime_installed")}
        ensure_wheel_runtime_installed
        """
    )

    env = os.environ.copy()
    env.update(
        {
            "runtimeRootPath": str(runtime_root),
            "runtimeWheelRootPath": str(runtime_wheel_root),
            "runtimeWheelVenvPath": str(runtime_venv),
            "envConfDir": str(env_conf_dir),
            "envDataDir": str(env_data_dir),
            "runtimeStaticRootPath": str(runtime_static_root),
            "wheelFilePath": str(wheel_file),
            "pythonInterpreter": str(fake_python),
            "PATH": os.environ["PATH"],
        }
    )

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert calls_log.read_text(encoding="utf-8").splitlines() == [
        f"pip:install --upgrade --force-reinstall {runtime_root / 'lx_annotate-0.0.3-py3-none-any.whl'}",
    ]


def test_ensure_runtime_vite_manifest_repairs_empty_manifest(tmp_path: Path):
    static_root = tmp_path / "static"
    manifest_path = static_root / ".vite" / "manifest.json"
    static_root.mkdir()
    manifest_path.parent.mkdir()
    manifest_path.write_text("", encoding="utf-8")
    (static_root / "main.js").write_text("console.log('ok')\n", encoding="utf-8")
    (static_root / "main.css").write_text("body{}\n", encoding="utf-8")

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        {_extract_function("ensure_runtime_vite_manifest")}
        ensure_runtime_vite_manifest "{manifest_path}" "{static_root}"
        """
    )

    result = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert manifest_path.read_text(encoding="utf-8") == textwrap.dedent(
        """\
        {
          "src/main.ts": {
            "file": "main.js",
            "isEntry": true,
            "css": [
              "main.css"
            ]
          }
        }
        """
    )
