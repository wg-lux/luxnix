from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "scripts.nix"
)
CONFIG_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "config.nix"
)
WHEEL_FILENAME = (
    "0123456789abcdef0123456789abcdef-lx_annotate-0.0.3-py3-none-any.whl"
)
CANONICAL_WHEEL_FILENAME = "lx_annotate-0.0.3-py3-none-any.whl"
PIP_INSTALL_PREFIX = "pip:install --upgrade"


def _extract_function(function_name: str, *, source_path: Path = SCRIPTS_NIX) -> str:
    source = source_path.read_text(encoding="utf-8")
    match = re.search(
        rf"^(?P<indent>[ \t]*){function_name}\(\) \{{\n",
        source,
        flags=re.MULTILINE,
    )
    assert match is not None, f"Could not locate {function_name} in {source_path}"
    indent = match.group("indent")
    lines = source[match.end() :].splitlines()
    body_lines: list[str] = []
    for line in lines:
        if line.rstrip() == f"{indent}}}":
            break
        body_lines.append(line)
    else:
        raise AssertionError(f"Could not locate end of {function_name} in {source_path}")

    body = textwrap.dedent("\n".join(body_lines))
    body = re.sub(r"\$\{pkgs\.[^}]+\}/bin/([A-Za-z0-9_.+-]+)", r"\1", body)
    body = re.sub(
        r'local wheelhouse_path="\$\{\s*optionalString '
        r'\(cfg\.runtime\.wheelhousePath != null\) '
        r'\(toString cfg\.runtime\.wheelhousePath\)\s*\}"',
        'local wheelhouse_path="${WHEELHOUSE_PATH:-}"',
        body,
        flags=re.DOTALL,
    )
    body = body.replace(
        'local wheel_dependency_overrides=${lib.escapeShellArg (lib.concatStringsSep " " cfg.runtime.wheelDependencyOverrides)}',
        'local wheel_dependency_overrides="${WHEEL_DEPENDENCY_OVERRIDES:-endoreg-db==1.0.1.8}"',
    )
    body = body.replace(
        'local wheel_dependency_overrides_hash=${lib.escapeShellArg (builtins.hashString "sha256" (lib.concatStringsSep "\\n" cfg.runtime.wheelDependencyOverrides))}',
        'local wheel_dependency_overrides_hash="${WHEEL_DEPENDENCY_OVERRIDES_HASH:-test-overrides-hash}"',
    )
    config_replacements = [
        (
            'local wheel_path=${lib.escapeShellArg wheelFilePath}',
            'local wheel_path="${wheelFilePath}"',
        ),
        (
            'local wheelhouse_path=${lib.escapeShellArg wheelhousePath}',
            'local wheelhouse_path="${WHEELHOUSE_PATH:-}"',
        ),
        (
            'local python_bin=${lib.escapeShellArg pythonInterpreter}',
            'local python_bin="${pythonInterpreter}"',
        ),
        (
            'local expected_package_version=${lib.escapeShellArg packageVersion}',
            'local expected_package_version="${EXPECTED_PACKAGE_VERSION:-0.0.3}"',
        ),
        (
            'local wheel_dependency_overrides=${lib.escapeShellArg wheelDependencyOverrideArgs}',
            'local wheel_dependency_overrides="${WHEEL_DEPENDENCY_OVERRIDES:-endoreg-db==1.0.1.8}"',
        ),
        (
            'local wheel_dependency_overrides_hash=${lib.escapeShellArg wheelDependencyOverrideHash}',
            'local wheel_dependency_overrides_hash="${WHEEL_DEPENDENCY_OVERRIDES_HASH:-test-overrides-hash}"',
        ),
        (
            '${lib.escapeShellArg "${runtimeRootPath}/.wheel-install.sha256"}',
            '"${runtimeRootPath}/.wheel-install.sha256"',
        ),
        (
            '${lib.escapeShellArg "${runtimeRootPath}/.wheel-install.lock"}',
            '"${runtimeRootPath}/.wheel-install.lock"',
        ),
        (
            '${lib.escapeShellArg "${runtimeRootPath}/pip-cache"}',
            '"${runtimeRootPath}/pip-cache"',
        ),
        (
            '${lib.escapeShellArg "${runtimeStaticRootPath}/.vite"}',
            '"${runtimeStaticRootPath}/.vite"',
        ),
        (
            '${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/python"}',
            '"${runtimeWheelVenvPath}/bin/python"',
        ),
        (
            '${lib.escapeShellArg "${runtimeWheelVenvPath}/bin/pip"}',
            '"${runtimeWheelVenvPath}/bin/pip"',
        ),
        (
            '${lib.escapeShellArg "${runtimeWheelVenvPath}/bin"}',
            '"${runtimeWheelVenvPath}/bin"',
        ),
        ('${lib.escapeShellArg runtimeRootPath}', '"${runtimeRootPath}"'),
        ('${lib.escapeShellArg runtimeWheelRootPath}', '"${runtimeWheelRootPath}"'),
        ('${lib.escapeShellArg runtimeWheelVenvPath}', '"${runtimeWheelVenvPath}"'),
        ('${lib.escapeShellArg envConfDir}', '"${envConfDir}"'),
        ('${lib.escapeShellArg envDataDir}', '"${envDataDir}"'),
        ('${lib.escapeShellArg runtimeStaticRootPath}', '"${runtimeStaticRootPath}"'),
        ('${helperPythonPath}', '${HELPER_PYTHON_PATH}'),
    ]
    for nix_expression, shell_expression in config_replacements:
        body = body.replace(nix_expression, shell_expression)
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
    wheel_file = tmp_path / WHEEL_FILENAME
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
            if [ "${{1:-}}" = "-c" ]; then
              printf '0.0.3\\n'
            fi
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
        {_extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)}
        lx_annotate_wheel_ensure
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
    assert runtime_root.joinpath("pip-cache").is_dir()
    assert calls_log.read_text(encoding="utf-8").splitlines() == [
        f"python:-m venv {runtime_venv}",
        f"{PIP_INSTALL_PREFIX} {runtime_root / CANONICAL_WHEEL_FILENAME}",
        f"pip:install --force-reinstall --no-deps {runtime_root / CANONICAL_WHEEL_FILENAME}",
        f"{PIP_INSTALL_PREFIX} --no-deps endoreg-db==1.0.1.8",
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
    wheel_file = tmp_path / WHEEL_FILENAME
    wheel_file.write_bytes(b"fake-wheel")
    calls_log = tmp_path / "calls.log"
    fake_python = tmp_path / "fake-python"
    existing_python = runtime_venv / "bin" / "python"
    existing_pip = runtime_venv / "bin" / "pip"
    existing_python.parent.mkdir(parents=True, exist_ok=True)
    _make_executable(
        existing_python,
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = \"-c\" ]; then printf '0.0.3\\n'; fi\n"
        "exit 0\n",
    )
    _make_executable(
        existing_pip,
        f"#!/usr/bin/env bash\nprintf 'pip:%s\\n' \"$*\" >> \"{calls_log}\"\nexit 0\n",
    )
    _make_executable(
        fake_python,
        (
            "#!/usr/bin/env bash\n"
            f"printf 'python:%s\\n' \"$*\" >> \"{calls_log}\"\n"
            "exit 1\n"
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
        {_extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)}
        lx_annotate_wheel_ensure
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
        f"{PIP_INSTALL_PREFIX} {runtime_root / CANONICAL_WHEEL_FILENAME}",
        f"pip:install --force-reinstall --no-deps {runtime_root / CANONICAL_WHEEL_FILENAME}",
        f"{PIP_INSTALL_PREFIX} --no-deps endoreg-db==1.0.1.8",
    ]


def test_ensure_wheel_runtime_installed_serializes_concurrent_install(tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    env_conf_dir = tmp_path / "conf"
    env_data_dir = tmp_path / "data"
    runtime_static_root = tmp_path / "static"
    wheel_file = tmp_path / WHEEL_FILENAME
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
            if [ "${{1:-}}" = "-c" ]; then
              printf '0.0.3\\n'
            fi
            exit 0
            EOF
              chmod +x "$target/bin/python"
              cat > "$target/bin/pip" <<'EOF'
            #!/usr/bin/env bash
            printf 'pip:%s\\n' "$*" >> "{calls_log}"
            sleep 0.2
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
        {_extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)}
        lx_annotate_wheel_ensure &
        pid1=$!
        lx_annotate_wheel_ensure &
        pid2=$!
        wait "$pid1"
        wait "$pid2"
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
    calls = calls_log.read_text(encoding="utf-8").splitlines()
    assert calls.count(f"python:-m venv {runtime_venv}") == 1
    expected_pip_call = (
        f"{PIP_INSTALL_PREFIX} {runtime_root / CANONICAL_WHEEL_FILENAME}"
    )
    assert calls.count(expected_pip_call) == 1
    expected_reinstall_call = (
        f"pip:install --force-reinstall --no-deps {runtime_root / CANONICAL_WHEEL_FILENAME}"
    )
    assert calls.count(expected_reinstall_call) == 1
    expected_override_call = f"{PIP_INSTALL_PREFIX} --no-deps endoreg-db==1.0.1.8"
    assert calls.count(expected_override_call) == 1


def test_ensure_wheel_runtime_installed_hashes_and_uses_wheelhouse(tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    runtime_venv.joinpath("bin").mkdir(parents=True)
    _make_executable(
        runtime_venv / "bin" / "python",
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = \"-c\" ]; then printf '0.0.3\\n'; fi\n"
        "exit 0\n",
    )

    calls_log = tmp_path / "calls.log"
    _make_executable(
        runtime_venv / "bin" / "pip",
        f"#!/usr/bin/env bash\nprintf 'pip:%s\\n' \"$*\" >> \"{calls_log}\"\n",
    )

    wheel_file = tmp_path / WHEEL_FILENAME
    wheel_file.write_bytes(b"fake-wheel")
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    wheelhouse.joinpath("dependency-1.0-py3-none-any.whl").write_bytes(b"dependency")

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        {_extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)}
        lx_annotate_wheel_ensure
        """
    )
    env = {
        **os.environ,
        "runtimeRootPath": str(runtime_root),
        "runtimeWheelRootPath": str(runtime_wheel_root),
        "runtimeWheelVenvPath": str(runtime_venv),
        "envConfDir": str(tmp_path / "conf"),
        "envDataDir": str(tmp_path / "data"),
        "runtimeStaticRootPath": str(tmp_path / "static"),
        "wheelFilePath": str(wheel_file),
        "pythonInterpreter": sys.executable,
        "WHEELHOUSE_PATH": str(wheelhouse),
    }

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    staged_wheel = runtime_root / CANONICAL_WHEEL_FILENAME
    wheelhouse_args = f"--no-index --find-links {wheelhouse}"
    assert calls_log.read_text(encoding="utf-8").splitlines() == [
        f"{PIP_INSTALL_PREFIX} {wheelhouse_args} {staged_wheel}",
        f"pip:install --force-reinstall --no-deps {staged_wheel}",
        f"{PIP_INSTALL_PREFIX} --no-deps {wheelhouse_args} endoreg-db==1.0.1.8",
    ]


def test_ensure_wheel_runtime_installed_rejects_metadata_version_mismatch(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    runtime_venv.joinpath("bin").mkdir(parents=True)
    _make_executable(
        runtime_venv / "bin" / "python",
        "#!/usr/bin/env bash\nprintf '0.0.4\\n'\n",
    )
    _make_executable(runtime_venv / "bin" / "pip", "#!/usr/bin/env bash\nexit 0\n")
    wheel_file = tmp_path / WHEEL_FILENAME
    wheel_file.write_bytes(b"fake-wheel")

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        {_extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)}
        lx_annotate_wheel_ensure
        """
    )
    env = {
        **os.environ,
        "runtimeRootPath": str(runtime_root),
        "runtimeWheelRootPath": str(runtime_wheel_root),
        "runtimeWheelVenvPath": str(runtime_venv),
        "envConfDir": str(tmp_path / "conf"),
        "envDataDir": str(tmp_path / "data"),
        "runtimeStaticRootPath": str(tmp_path / "static"),
        "wheelFilePath": str(wheel_file),
        "pythonInterpreter": sys.executable,
    }

    result = subprocess.run(
        ["bash", "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "Installed lx-annotate version 0.0.4 does not match configured "
        "runtime.packageVersion 0.0.3."
    ) in result.stderr


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
        {_extract_function("ensure_runtime_vite_manifest", source_path=SCRIPTS_NIX)}
        ensure_runtime_vite_manifest "{manifest_path}" "{static_root}"
        """
    )

    result = subprocess.run(
        ["bash", "-c", script],
        env={**os.environ, "HELPER_PYTHON_PATH": sys.executable},
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
