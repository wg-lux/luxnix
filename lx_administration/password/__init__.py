"""Public, lazily loaded password utilities."""

from typing import TYPE_CHECKING

from .._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .generator import PasswordGenerator

__all__ = ["PasswordGenerator"]

_EXPORTS = {
    "PasswordGenerator": (".generator", "PasswordGenerator"),
}


def __getattr__(name: str) -> object:
    """Resolve password helpers without importing Faker and Passlib eagerly."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
