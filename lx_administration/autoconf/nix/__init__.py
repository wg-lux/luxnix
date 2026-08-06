"""Public Autoconf rendering stage without eager renderer imports."""

from typing import TYPE_CHECKING

from ..._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .main import render_configurations

__all__ = ["render_configurations"]

_EXPORTS = {
    "render_configurations": (".main", "render_configurations"),
}


def __getattr__(name: str) -> object:
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
