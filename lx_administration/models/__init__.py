"""Lazy public API for the administration data models."""

from typing import TYPE_CHECKING

from .._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .ansible.facts import AnsibleFactsModel
    from .ansible.inventory import AnsibleInventoryGroup, AnsibleInventoryHost
    from .ansible.merged_host_vars import MergedHostVars
    from .facts import HostConfigModel
    from .hardware import BiosModel, NetworkInterfaceModel
    from .vault import AnsibleCfg, Secret, Vault

__all__ = [
    "AnsibleFactsModel",
    "BiosModel",
    "NetworkInterfaceModel",
    "HostConfigModel",
    "AnsibleInventoryHost",
    "AnsibleInventoryGroup",
    "MergedHostVars",
    "Vault",
    "Secret",
    "AnsibleCfg",
]

_EXPORTS = {
    "AnsibleFactsModel": (".ansible.facts", "AnsibleFactsModel"),
    "BiosModel": (".hardware", "BiosModel"),
    "NetworkInterfaceModel": (".hardware", "NetworkInterfaceModel"),
    "HostConfigModel": (".facts", "HostConfigModel"),
    "AnsibleInventoryHost": (".ansible.inventory", "AnsibleInventoryHost"),
    "AnsibleInventoryGroup": (".ansible.inventory", "AnsibleInventoryGroup"),
    "MergedHostVars": (".ansible.merged_host_vars", "MergedHostVars"),
    "Vault": (".vault", "Vault"),
    "Secret": (".vault", "Secret"),
    "AnsibleCfg": (".vault", "AnsibleCfg"),
}


def __getattr__(name: str) -> object:
    """Load a model family only when its public export is requested."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
