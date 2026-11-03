"""Backend policy failures must prevent the actual console entrypoint running."""
from pathlib import Path
import subprocess
import venv

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / 'modules/nixos/services/lx-annotate-local/scripts/hub-oidc-entrypoint.py'


@pytest.fixture
def runtime(tmp_path):
    home = tmp_path / 'runtime'
    venv.EnvBuilder(with_pip=False).create(home)
    python = home / 'bin/python'
    site = Path(subprocess.check_output([str(python), '-c',
                'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip())
    authz = site / 'endoreg_db/authz'
    authz.mkdir(parents=True)
    (authz.parent / '__init__.py').touch()
    (authz / '__init__.py').touch()
    target = home / 'bin/console'
    marker = tmp_path / 'started'
    target.write_text('import sys\nfrom pathlib import Path\n'
                      'from endoreg_db.authz import middleware\n'
                      'assert middleware.PUBLIC_PREFIXES == ("/health/", "/api/media/hub/transfers/")\n'
                      'Path(sys.argv[1]).write_text("|".join(sys.argv[2:]))\n'
                      'raise SystemExit(23)\n')
    return python, authz / 'middleware.py', target, marker


@pytest.mark.parametrize('optimized', [False, True])
@pytest.mark.parametrize('definition', ['PUBLIC_PREFIXES = []', 'PUBLIC_PREFIXES = (None,)',
                                        'raise ImportError("incompatible backend")', ''])
def test_contract_failure_aborts_before_application(runtime, optimized, definition):
    python, middleware, target, marker = runtime
    middleware.write_text(definition)
    result = subprocess.run([str(python), *(['-O'] if optimized else []), str(LAUNCHER),
                             str(target), str(marker)], capture_output=True, text=True)
    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize('prefixes', ['("/health/",)', '("/health/", "/api/media/hub/transfers/")'])
def test_explicit_startup_preserves_routes_arguments_and_exit_status(runtime, prefixes):
    python, middleware, target, marker = runtime
    middleware.write_text('PUBLIC_PREFIXES = ' + prefixes)
    result = subprocess.run([str(python), str(LAUNCHER), str(target), str(marker),
                             'path with spaces', '*'], capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    assert marker.read_text() == 'path with spaces|*'


def test_wheel_calls_checked_launcher_without_global_sitecustomize():
    source = (ROOT / 'modules/nixos/services/lx-annotate-local/config.nix').read_text()
    assert 'lx_annotate_wheel_exec ${lib.escapeShellArg' in source
    assert '${./scripts/hub-oidc-entrypoint.py} "$@"' in source
    assert 'writeTextDir "sitecustomize.py"' not in source
    assert 'PYTHONPATH = toString hubOidcMiddlewarePolicy' not in source


def test_nonwheel_hub_cannot_bypass_checked_startup():
    from nix_eval_helpers import eval_json

    result = eval_json('''
      let f = builtins.getFlake "__LUXNIX_FLAKE_URI__";
          c = (f.nixosConfigurations.gs-02.extendModules { modules = [
            ({lib,...}: {
              services.luxnix.lxAnnotateLocal.runtime.mode = lib.mkForce "repo";
            })
          ]; }).config;
      in {
        transfer = c.services.luxnix.lxAnnotateLocal.hub.transferApi.enable;
        rejected = builtins.any (a: !a.assertion &&
          f.inputs.nixpkgs.lib.hasPrefix "Hub transfer authentication" a.message) c.assertions;
        injected = c.systemd.services.lx-annotate.environment ? PYTHONPATH;
      }
    ''')
    assert result == {'transfer': True, 'rejected': True, 'injected': False}
