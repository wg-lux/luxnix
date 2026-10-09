from typing import TYPE_CHECKING

from .._lazy_exports import public_names, resolve_lazy_export

if TYPE_CHECKING:
    from .checkfile import CheckFile, apply_checks, load_check_files
    from .dump import (
        PRIVATE_DIRECTORY_MODE,
        PRIVATE_FILE_MODE,
        ansible_lint,
        dump_yaml,
        format_yaml,
    )
    from .loading import load_unique_yaml, load_unique_yaml_file

__all__ = [
    "CheckFile",
    "load_check_files",
    "apply_checks",
    "dump_yaml",
    "format_yaml",
    "ansible_lint",
    "PRIVATE_DIRECTORY_MODE",
    "PRIVATE_FILE_MODE",
    "load_unique_yaml",
    "load_unique_yaml_file",
]

_EXPORTS = {
    "CheckFile": (".checkfile", "CheckFile"),
    "load_check_files": (".checkfile", "load_check_files"),
    "apply_checks": (".checkfile", "apply_checks"),
    "dump_yaml": (".dump", "dump_yaml"),
    "format_yaml": (".dump", "format_yaml"),
    "ansible_lint": (".dump", "ansible_lint"),
    "PRIVATE_DIRECTORY_MODE": (".dump", "PRIVATE_DIRECTORY_MODE"),
    "PRIVATE_FILE_MODE": (".dump", "PRIVATE_FILE_MODE"),
    "load_unique_yaml": (".loading", "load_unique_yaml"),
    "load_unique_yaml_file": (".loading", "load_unique_yaml_file"),
}


def __getattr__(name: str) -> object:
    """Load YAML helpers without importing unrelated formatters or models."""
    return resolve_lazy_export(
        name,
        package_name=__name__,
        exports=_EXPORTS,
        namespace=globals(),
    )


def __dir__() -> list[str]:
    return public_names(globals(), _EXPORTS)
