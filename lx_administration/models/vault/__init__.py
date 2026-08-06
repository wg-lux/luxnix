"""Public, lazily loaded Vault model API."""

from typing import TYPE_CHECKING

from ..._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .admin_passwords import import_admin_passwords, load_admin_passwords
    from .ansible_cfg import AnsibleCfg
    from .manager import Vault
    from .psk import PreSharedKey
    from .secret import Secret
    from .secret_template import SecretTemplate

__all__ = [
    "Vault",
    "PreSharedKey",
    "Secret",
    "SecretTemplate",
    "AnsibleCfg",
    "load_admin_passwords",
    "import_admin_passwords",
]

_EXPORTS = {
    "Vault": (".manager", "Vault"),
    "PreSharedKey": (".psk", "PreSharedKey"),
    "Secret": (".secret", "Secret"),
    "SecretTemplate": (".secret_template", "SecretTemplate"),
    "AnsibleCfg": (".ansible_cfg", "AnsibleCfg"),
    "load_admin_passwords": (".admin_passwords", "load_admin_passwords"),
    "import_admin_passwords": (".admin_passwords", "import_admin_passwords"),
}


def __getattr__(name: str) -> object:
    """Resolve Vault models only when callers request them."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
