"""Public, lazily loaded API for the LuxNix Autoconf pipeline."""

from typing import TYPE_CHECKING

from .._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .config import (
        AUTOCONF_OPTION_NAMES,
        DEFAULT_CONFIG_PATH,
        AutoconfConfig,
    )
    from .errors import (
        AnsibleFactFormatError,
        AutoconfConfigError,
        AutoconfPipelineError,
        AutoconfSourceError,
        AutoconfSourceNotFoundError,
        AutoconfYamlError,
    )
    from .layout import (
        AnsibleInventoryLayout,
        AutoconfOutputLayout,
        AutoconfSourceLayout,
        NixOutputLayout,
        NixTemplateLayout,
    )
    from .main import run_from_config

__all__ = [
    "AUTOCONF_OPTION_NAMES",
    "AnsibleFactFormatError",
    "AnsibleInventoryLayout",
    "DEFAULT_CONFIG_PATH",
    "AutoconfConfig",
    "AutoconfConfigError",
    "AutoconfOutputLayout",
    "AutoconfSourceLayout",
    "AutoconfPipelineError",
    "AutoconfSourceError",
    "AutoconfSourceNotFoundError",
    "AutoconfYamlError",
    "NixOutputLayout",
    "NixTemplateLayout",
    "run_from_config",
]

_EXPORTS = {
    "AUTOCONF_OPTION_NAMES": (".config", "AUTOCONF_OPTION_NAMES"),
    "AnsibleFactFormatError": (".errors", "AnsibleFactFormatError"),
    "AnsibleInventoryLayout": (".layout", "AnsibleInventoryLayout"),
    "DEFAULT_CONFIG_PATH": (".config", "DEFAULT_CONFIG_PATH"),
    "AutoconfConfig": (".config", "AutoconfConfig"),
    "AutoconfConfigError": (".errors", "AutoconfConfigError"),
    "AutoconfOutputLayout": (".layout", "AutoconfOutputLayout"),
    "AutoconfSourceLayout": (".layout", "AutoconfSourceLayout"),
    "AutoconfPipelineError": (".errors", "AutoconfPipelineError"),
    "AutoconfSourceError": (".errors", "AutoconfSourceError"),
    "AutoconfSourceNotFoundError": (
        ".errors",
        "AutoconfSourceNotFoundError",
    ),
    "AutoconfYamlError": (".errors", "AutoconfYamlError"),
    "NixOutputLayout": (".layout", "NixOutputLayout"),
    "NixTemplateLayout": (".layout", "NixTemplateLayout"),
    "run_from_config": (".main", "run_from_config"),
}


def __getattr__(name: str) -> object:
    """Load configuration or pipeline code only when requested."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
