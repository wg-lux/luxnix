"""Public Autoconf import helpers without eager pipeline imports."""

from typing import TYPE_CHECKING

from ..._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from ..errors import AnsibleFactFormatError
    from .ansible_facts import load_all_host_facts
    from .ansible_inventory import load_inventory_hostfile
    from .main import (
        build_home_merged_variables,
        build_system_merged_variables,
        import_source_data,
    )

__all__ = [
    "AnsibleFactFormatError",
    "import_source_data",
    "build_system_merged_variables",
    "build_home_merged_variables",
    "load_all_host_facts",
    "load_inventory_hostfile",
]

_EXPORTS = {
    "AnsibleFactFormatError": ("..errors", "AnsibleFactFormatError"),
    "import_source_data": (".main", "import_source_data"),
    "build_system_merged_variables": (
        ".main",
        "build_system_merged_variables",
    ),
    "build_home_merged_variables": (
        ".main",
        "build_home_merged_variables",
    ),
    "load_all_host_facts": (".ansible_facts", "load_all_host_facts"),
    "load_inventory_hostfile": (
        ".ansible_inventory",
        "load_inventory_hostfile",
    ),
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
