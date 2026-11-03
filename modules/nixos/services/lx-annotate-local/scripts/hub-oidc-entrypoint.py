"""Explicit wheel startup bridge until the backend owns hub OIDC route policy.

A failure here terminates the console entrypoint before application code runs.
Unlike sitecustomize, Python cannot suppress a failed compatibility check.
"""
import os
from pathlib import Path
import runpy
import sys


def install_policy():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lx_annotate.settings.settings_prod')
    from endoreg_db.authz import middleware

    prefix = '/api/media/hub/transfers/'
    prefixes = getattr(middleware, 'PUBLIC_PREFIXES', None)
    if not isinstance(prefixes, tuple) or any(not isinstance(p, str) for p in prefixes):
        raise RuntimeError('Unsupported backend OIDC route policy; application startup refused')
    if prefix not in prefixes:
        middleware.PUBLIC_PREFIXES = (*prefixes, prefix)


def main():
    target = Path(sys.argv[1])
    if not target.is_absolute() or target.parent != Path(sys.executable).parent:
        raise ValueError('Expected an installed console entrypoint beside the runtime Python')
    install_policy()
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main()
