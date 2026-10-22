from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import textwrap
import venv
from zipfile import ZipFile

import pytest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "scripts.nix"
)
CONFIG_NIX = (
    REPO_ROOT / "modules" / "nixos" / "services" / "lx-annotate-local" / "config.nix"
)
WHEEL_FILENAME = "0123456789abcdef0123456789abcdef-lx_annotate-0.0.3-py3-none-any.whl"
CANONICAL_WHEEL_FILENAME = "lx_annotate-0.0.3-py3-none-any.whl"
PIP_INSTALL_PREFIX = "pip:install --upgrade"


@pytest.mark.parametrize("broken", [False, True])
def test_python_repair_preserves_downgrade_evidence(tmp_path: Path, broken: bool):
    root = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, symlinks=True).create(root)
    python = root / "bin/python"
    site = root / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    metadata = site / "lx_annotate-1.5.5.dist-info/METADATA"
    metadata.parent.mkdir()
    metadata.write_text("Name: lx-annotate\nVersion: 1.5.5\n")
    old = tmp_path / "old-python"
    old.symlink_to(sys.executable)
    python.unlink()
    python.symlink_to(old)
    if broken:
        old.unlink()
    helper = CONFIG_NIX.parent / "scripts/wheel-python-repair.py"
    subprocess.run([sys.executable, str(helper), str(root)], check=True)
    assert python.resolve() == Path(sys.executable).resolve()
    assert metadata.read_text() == "Name: lx-annotate\nVersion: 1.5.5\n"
    guard_path = CONFIG_NIX.parent / "scripts/wheel-downgrade-guard.py"
    result = subprocess.run(
        [str(python), "-c", f"import runpy; g = runpy.run_path({str(guard_path)!r}); "
         "g['reject_downgrade']('lx-annotate', g['Version']('1.5.4'), g['installed_versions']())"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Refusing shared-runtime downgrade: lx-annotate 1.5.5 -> 1.5.4" in result.stderr


def test_python_repair_rejects_abi_change_without_mutation(tmp_path: Path):
    root = tmp_path / "venv"
    (root / "bin").mkdir(parents=True)
    (root / "pyvenv.cfg").write_text("version = 2.7.18\n")
    python = root / "bin/python"
    python.symlink_to("/missing/interpreter")
    result = subprocess.run(
        [sys.executable, str(CONFIG_NIX.parent / "scripts/wheel-python-repair.py"), str(root)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "explicit runtime migration" in result.stderr
    assert os.readlink(python) == "/missing/interpreter"


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
        raise AssertionError(
            f"Could not locate end of {function_name} in {source_path}"
        )

    body = textwrap.dedent("\n".join(body_lines))
    body = re.sub(r"\$\{pkgs\.[^}]+\}/bin/([A-Za-z0-9_.+-]+)", r"\1", body)
    body = re.sub(
        r'local wheelhouse_path="\$\{\s*optionalString '
        r"\(cfg\.runtime\.wheelhousePath != null\) "
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
        ("${wheelDowngradeGuard}", "/test-wheel-downgrade-guard"),
        ("${lib.escapeShellArg (builtins.toJSON wheelDependencyOverrides)}", "'[]'"),
        (
            '${lib.escapeShellArg "${runtimeRootPath}/.wheel-application.constraints"}',
            '"${runtimeRootPath}/.wheel-application.constraints"',
        ),
        (
            '${lib.escapeShellArg "${runtimeRootPath}/.wheel-overrides.constraints"}',
            '"${runtimeRootPath}/.wheel-overrides.constraints"',
        ),
        (
            "local wheel_path=${lib.escapeShellArg wheelFilePath}",
            'local wheel_path="${wheelFilePath}"',
        ),
        (
            "local wheelhouse_path=${lib.escapeShellArg wheelhousePath}",
            'local wheelhouse_path="${WHEELHOUSE_PATH:-}"',
        ),
        (
            "local python_bin=${lib.escapeShellArg pythonInterpreter}",
            'local python_bin="${pythonInterpreter}"',
        ),
        (
            "local expected_package_version=${lib.escapeShellArg packageVersion}",
            'local expected_package_version="${EXPECTED_PACKAGE_VERSION:-0.0.3}"',
        ),
        (
            "local wheel_dependency_overrides=${lib.escapeShellArg wheelDependencyOverrideArgs}",
            'local wheel_dependency_overrides="${WHEEL_DEPENDENCY_OVERRIDES:-endoreg-db==1.0.1.8}"',
        ),
        (
            "local wheel_dependency_overrides_hash=${lib.escapeShellArg wheelDependencyOverrideHash}",
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
        ("${lib.escapeShellArg runtimeRootPath}", '"${runtimeRootPath}"'),
        ("${lib.escapeShellArg runtimeWheelRootPath}", '"${runtimeWheelRootPath}"'),
        ("${lib.escapeShellArg runtimeWheelVenvPath}", '"${runtimeWheelVenvPath}"'),
        ("${lib.escapeShellArg envConfDir}", '"${envConfDir}"'),
        ("${lib.escapeShellArg envDataDir}", '"${envDataDir}"'),
        ("${lib.escapeShellArg runtimeStaticRootPath}", '"${runtimeStaticRootPath}"'),
        ("${helperPythonPath}", "${HELPER_PYTHON_PATH}"),
    ]
    for nix_expression, shell_expression in config_replacements:
        body = body.replace(nix_expression, shell_expression)
    body = body.replace("${./scripts/wheel-python-repair.py}", str(CONFIG_NIX.parent / "scripts/wheel-python-repair.py"))
    body = body.replace('${lib.escapeShellArg "${runtimeWheelVenvPath}/pyvenv.cfg"}', '"${runtimeWheelVenvPath}/pyvenv.cfg"')
    body = body.replace("''${", "${")
    return f"{function_name}() {{\n{body}\n}}"


def _make_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.mark.parametrize("command", [
    "lx-annotate-recover-data", "lx-annotate-provision-hub-nodes",
    "lx-annotate-storage-relief", "lx-annotate-acceptance", "lx-annotate-check-static",
])
@pytest.mark.parametrize("runtime_state", ["prepared", "unprepared", "missing-command"])
def test_operational_wrappers_use_prepared_wheel(
    tmp_path: Path, command: str, runtime_state: str,
):
    out = tmp_path / "wrapper"
    runtime = tmp_path / "venv"
    (out / "bin").mkdir(parents=True)
    (out / "libexec").mkdir()
    (runtime / "bin").mkdir(parents=True)
    log = tmp_path / "calls.log"
    (out / "libexec/lx-annotate-wheel-runtime-lib").write_text(
        'lx_annotate_wheel_ensure() {\n'
        '  test "$LX_ANNOTATE_WHEEL_INSTALL_ALLOWED" = false || exit 90\n'
        '  printf "ensure\\n" >> "$CALLS_LOG"\n'
        '  test "$RUNTIME_STATE" != unprepared || exit 91\n'
        '}\n'
        'lx_annotate_wheel_export_secret_env() { printf "env\\n" >> "$CALLS_LOG"; }\n'
        'lx_annotate_wheel_sync_static() { exit 92; }\n'
    )
    if runtime_state != "missing-command":
        _make_executable(runtime / "bin" / command,
                         '#!/usr/bin/env bash\nprintf "arg:%s\\n" "$@" >> "$CALLS_LOG"\nexit 23\n')
    call = re.search(rf"^    make_entrypoint {re.escape(command)} .+$",
                     CONFIG_NIX.read_text(), re.MULTILINE)
    assert call is not None, f"Missing wheel wrapper for {command}"
    env = dict(os.environ, out=str(out), runtimeWheelVenvPath=str(runtime),
               CALLS_LOG=str(log), RUNTIME_STATE=runtime_state)
    subprocess.run(["bash", "-eu", "-c",
                    _extract_function("make_entrypoint", source_path=CONFIG_NIX)
                    + "\n" + call.group()], env=env, check=True)
    result = subprocess.run(
        ["bash", str(out / "bin" / command), "--config", "path with spaces", "*"],
        env=env, capture_output=True, text=True,
    )
    if runtime_state == "prepared":
        assert result.returncode == 23
        assert log.read_text().splitlines() == [
            "ensure", "env", "arg:--config", "arg:path with spaces", "arg:*",
        ]
    elif runtime_state == "unprepared":
        assert result.returncode == 91
        assert log.read_text().splitlines() == ["ensure"]
    else:
        assert result.returncode == 1
        assert f"does not expose console script: {command}" in result.stderr
        assert log.read_text().splitlines() == ["ensure", "env"]


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
        f"{PIP_INSTALL_PREFIX} {runtime_root / CANONICAL_WHEEL_FILENAME}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}",
        "pip:install --force-reinstall --no-deps "
        f"{runtime_root / CANONICAL_WHEEL_FILENAME}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}",
        f"{PIP_INSTALL_PREFIX} --no-deps endoreg-db==1.0.1.8 --force-reinstall"
        f" --constraint {runtime_root / '.wheel-overrides.constraints'}",
    ]
    assert f"venv={runtime_venv}" in result.stdout
    assert f"app_root={runtime_wheel_root}" in result.stdout
    assert "hash=" in result.stdout


def test_application_entrypoint_refuses_to_install_unprepared_runtime(tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    wheel_file = tmp_path / WHEEL_FILENAME
    wheel_file.write_bytes(b"fake-wheel")
    calls_log = tmp_path / "calls.log"
    fake_python = tmp_path / "fake-python"
    _make_executable(
        fake_python,
        f'#!/usr/bin/env bash\nprintf \'python:%s\\n\' "$*" >> "{calls_log}"\n',
    )

    script = textwrap.dedent(
        f"""\
        set -euo pipefail
        {_extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)}
        export LX_ANNOTATE_WHEEL_INSTALL_ALLOWED=false
        lx_annotate_wheel_ensure
        """
    )
    env = os.environ.copy()
    env.update(
        {
            "runtimeRootPath": str(runtime_root),
            "runtimeWheelRootPath": str(runtime_wheel_root),
            "runtimeWheelVenvPath": str(runtime_venv),
            "envConfDir": str(tmp_path / "conf"),
            "envDataDir": str(tmp_path / "data"),
            "runtimeStaticRootPath": str(tmp_path / "static"),
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

    assert result.returncode != 0
    assert "wheel runtime is not prepared" in result.stderr
    assert not runtime_venv.joinpath("bin", "python").exists()
    assert not calls_log.exists()


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
        'if [ "${1:-}" = "-c" ]; then printf \'0.0.3\\n\'; fi\n'
        "exit 0\n",
    )
    _make_executable(
        existing_pip,
        f'#!/usr/bin/env bash\nprintf \'pip:%s\\n\' "$*" >> "{calls_log}"\nexit 0\n',
    )
    _make_executable(
        fake_python,
        (
            "#!/usr/bin/env bash\n"
            f'printf \'python:%s\\n\' "$*" >> "{calls_log}"\n'
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
        f"{PIP_INSTALL_PREFIX} {runtime_root / CANONICAL_WHEEL_FILENAME}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}",
        "pip:install --force-reinstall --no-deps "
        f"{runtime_root / CANONICAL_WHEEL_FILENAME}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}",
        f"{PIP_INSTALL_PREFIX} --no-deps endoreg-db==1.0.1.8 --force-reinstall"
        f" --constraint {runtime_root / '.wheel-overrides.constraints'}",
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
        f" --constraint {runtime_root / '.wheel-application.constraints'}"
    )
    assert calls.count(expected_pip_call) == 1
    expected_reinstall_call = (
        "pip:install --force-reinstall --no-deps "
        f"{runtime_root / CANONICAL_WHEEL_FILENAME}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}"
    )
    assert calls.count(expected_reinstall_call) == 1
    expected_override_call = (
        f"{PIP_INSTALL_PREFIX} --no-deps endoreg-db==1.0.1.8 --force-reinstall"
        f" --constraint {runtime_root / '.wheel-overrides.constraints'}"
    )
    assert calls.count(expected_override_call) == 1


def test_ensure_wheel_runtime_installed_hashes_and_uses_wheelhouse(tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    runtime_wheel_root = runtime_root / "wheel-app"
    runtime_venv = runtime_wheel_root / ".venv"
    runtime_venv.joinpath("bin").mkdir(parents=True)
    _make_executable(
        runtime_venv / "bin" / "python",
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "-c" ]; then printf \'0.0.3\\n\'; fi\n'
        "exit 0\n",
    )

    calls_log = tmp_path / "calls.log"
    _make_executable(
        runtime_venv / "bin" / "pip",
        f'#!/usr/bin/env bash\nprintf \'pip:%s\\n\' "$*" >> "{calls_log}"\n',
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
        f"{PIP_INSTALL_PREFIX} {wheelhouse_args} {staged_wheel}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}",
        f"pip:install --force-reinstall --no-deps {staged_wheel}"
        f" --constraint {runtime_root / '.wheel-application.constraints'}",
        f"{PIP_INSTALL_PREFIX} --no-deps {wheelhouse_args} "
        "endoreg-db==1.0.1.8 --force-reinstall"
        f" --constraint {runtime_root / '.wheel-overrides.constraints'}",
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




@pytest.mark.parametrize("install_allowed", ["true", "false"])
def test_installer_repairs_collected_python_only_in_preparation_unit(tmp_path: Path, install_allowed: str):
    root = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True, symlinks=True).create(root)
    site = root / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    metadata = site / "lx_annotate-1.5.5.dist-info/METADATA"
    metadata.parent.mkdir()
    metadata.write_text("Name: lx-annotate\nVersion: 1.5.5\n")
    python = root / "bin/python"
    python.unlink()
    python.symlink_to("/missing/collected-python")
    wheel = tmp_path / CANONICAL_WHEEL_FILENAME
    with ZipFile(wheel, "w") as archive:
        archive.writestr("lx_annotate-0.0.3.dist-info/METADATA", "Name: lx-annotate\nVersion: 0.0.3\n")
    script = _extract_function("lx_annotate_wheel_ensure", source_path=CONFIG_NIX)
    script = script.replace("/test-wheel-downgrade-guard/guard.py", str(CONFIG_NIX.parent / "scripts/wheel-downgrade-guard.py"))
    result = subprocess.run(
        ["bash", "-c", script + "\nlx_annotate_wheel_ensure"],
        env={**os.environ, "runtimeRootPath": str(tmp_path / "runtime"),
             "runtimeWheelRootPath": str(tmp_path / "app"), "runtimeWheelVenvPath": str(root),
             "envConfDir": str(tmp_path / "conf"), "envDataDir": str(tmp_path / "data"),
             "runtimeStaticRootPath": str(tmp_path / "static"), "wheelFilePath": str(wheel),
             "pythonInterpreter": sys.executable, "LX_ANNOTATE_WHEEL_INSTALL_ALLOWED": install_allowed},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert not (tmp_path / "runtime/.wheel-install.sha256").exists()
    if install_allowed == "true":
        assert python.resolve() == Path(sys.executable).resolve()
        assert "Refusing shared-runtime downgrade: lx-annotate 1.5.5 -> 0.0.3" in result.stderr
    else:
        assert os.readlink(python) == "/missing/collected-python"
        assert "not prepared for this release" in result.stderr


@pytest.mark.parametrize("version", ["1.5.7", "1.5.4"])
def test_release_version_must_match_selected_wheel(version: str):
    from nix_eval_helpers import eval_result

    result = eval_result('''
      let
        f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
        c = (f.nixosConfigurations.gc-10.extendModules {
          modules = [({ lib, ... }: {
            services.luxnix.lxAnnotateLocal.runtime = {
              wheelPath = lib.mkForce /test/lx_annotate-1.5.7-py3-none-any.whl;
              packageVersion = lib.mkForce "%s";
            };
          })];
        }).config;
      in c.services.luxnix.lxAnnotateLocal.runtime.packageVersion
    ''' % version)
    if version == "1.5.7":
        assert result.returncode == 0, result.stderr
        assert '"1.5.7"' in result.stdout
    else:
        assert result.returncode != 0
        assert "runtime.packageVersion must match runtime.wheelPath" in result.stderr
