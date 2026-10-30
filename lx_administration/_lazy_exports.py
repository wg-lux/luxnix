"""Shared support for lightweight public package facades."""

from importlib import import_module
from typing import Any, Mapping, MutableMapping


LazyExports = Mapping[str, tuple[str, str]]


def resolve_lazy_export(
    name: str,
    *,
    package_name: str,
    exports: LazyExports,
    namespace: MutableMapping[str, Any],
) -> object:
    """Resolve and cache one named public export from a relative module."""
    try:
        module_name, attribute_name = exports[name]
    except KeyError as error:
        message = f"module {package_name!r} has no attribute {name!r}"
        raise AttributeError(message) from error

    value = getattr(import_module(module_name, package_name), attribute_name)
    namespace[name] = value
    return value


def public_names(namespace: Mapping[str, object], exports: LazyExports) -> list[str]:
    """Return normal module names plus its declared lazy exports."""
    return sorted((*namespace, *exports))
