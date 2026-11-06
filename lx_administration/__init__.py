from typing import TYPE_CHECKING

from ._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .password import PasswordGenerator
    from .ssh import create_openssh_keys

__all__ = ["create_openssh_keys", "PasswordGenerator"]

_EXPORTS = {
    "create_openssh_keys": (".ssh", "create_openssh_keys"),
    "PasswordGenerator": (".password", "PasswordGenerator"),
}


def __getattr__(name: str) -> object:
    """Load public utilities without importing unrelated subsystems eagerly."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
