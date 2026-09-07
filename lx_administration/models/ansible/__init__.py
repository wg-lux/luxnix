"""Lazy public API for inventory and Ansible-facts models."""

from typing import TYPE_CHECKING

from ..._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .facts import AnsibleFactsModel
    from ..hardware import BiosModel, NetworkInterfaceModel
    from .inventory import (
        AnsibleInventory,
        AnsibleInventoryGroup,
        AnsibleInventoryHost,
    )
    from .merged_host_vars import MergedHostVars

__all__ = [
    "AnsibleInventory",
    "AnsibleInventoryGroup",
    "AnsibleInventoryHost",
    "AnsibleFactsModel",
    "BiosModel",
    "NetworkInterfaceModel",
    "MergedHostVars",
]

_EXPORTS = {
    "AnsibleInventory": (".inventory", "AnsibleInventory"),
    "AnsibleInventoryGroup": (".inventory", "AnsibleInventoryGroup"),
    "AnsibleInventoryHost": (".inventory", "AnsibleInventoryHost"),
    "AnsibleFactsModel": (".facts", "AnsibleFactsModel"),
    "BiosModel": ("..hardware", "BiosModel"),
    "NetworkInterfaceModel": ("..hardware", "NetworkInterfaceModel"),
    "MergedHostVars": (".merged_host_vars", "MergedHostVars"),
}


def __getattr__(name: str) -> object:
    """Load an Ansible model family only when its export is requested."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
