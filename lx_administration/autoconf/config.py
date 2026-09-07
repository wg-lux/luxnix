from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

from lx_administration.yaml import load_unique_yaml_file

from .errors import AutoconfConfigError
from .layout import (
    AnsibleInventoryLayout,
    AutoconfOutputLayout,
    AutoconfSourceLayout,
    NixOutputLayout,
    NixTemplateLayout,
)

__all__ = [
    "AUTOCONF_OPTION_NAMES",
    "DEFAULT_CONFIG_PATH",
    "AnsibleInventoryLayout",
    "AutoconfConfig",
    "AutoconfConfigError",
    "AutoconfOutputLayout",
    "AutoconfSourceLayout",
    "NixOutputLayout",
    "NixTemplateLayout",
]

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "autoconf" / "config.yml"
_OPTION_FIELDS = (
    ("paths.ansible_root", "ansible_root"),
    ("paths.output", "output"),
    ("paths.nix_output", "nix_output"),
    ("paths.nix_templates", "nix_templates"),
    ("paths.report_output", "report_output"),
    ("inventory.subnet", "inventory_subnet"),
    ("inventory.system_group", "inventory_system_group"),
    ("home.default_users", "home_default_users"),
    ("home.state_version", "home_state_version"),
)
_OPTION_FIELD_BY_NAME = dict(_OPTION_FIELDS)
AUTOCONF_OPTION_NAMES = tuple(name for name, _ in _OPTION_FIELDS)
_SECTION_KEYS = {
    section: frozenset(
        name.removeprefix(f"{section}.")
        for name in AUTOCONF_OPTION_NAMES
        if name.startswith(f"{section}.")
    )
    for section in ("paths", "inventory", "home")
}


def _mapping(value: object, option: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise AutoconfConfigError(f"'{option}' must be a YAML mapping")
    if any(not isinstance(key, str) for key in value):
        raise AutoconfConfigError(f"'{option}' keys must be strings")
    return cast("Mapping[str, object]", value)


def _only_keys(
    value: Mapping[str, object],
    allowed: Collection[str],
    option: str,
) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        names = ", ".join(unknown)
        raise AutoconfConfigError(f"Unknown option(s) in '{option}': {names}")


def _required_section(
    root: Mapping[str, object],
    section: str,
) -> Mapping[str, object]:
    """Load one complete, known configuration section."""
    values = _mapping(root.get(section), section)
    required = _SECTION_KEYS[section]
    _only_keys(values, required, section)
    missing = sorted(required - set(values))
    if missing:
        raise AutoconfConfigError(
            f"Missing option(s) in '{section}': {', '.join(missing)}"
        )
    return values


def _relative_path(value: object, option: str, base_dir: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AutoconfConfigError(f"'{option}' must be a non-empty path string")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _subnet(value: object) -> str:
    if not isinstance(value, str):
        raise AutoconfConfigError("'inventory.subnet' must be a string")
    octets = value.removesuffix(".").split(".")
    if not value.endswith(".") or len(octets) != 3:
        raise AutoconfConfigError(
            "'inventory.subnet' must be an IPv4 prefix ending in '.', "
            "for example 172.16.255."
        )
    if any(not octet.isdigit() or not 0 <= int(octet) <= 255 for octet in octets):
        raise AutoconfConfigError("'inventory.subnet' contains an invalid IPv4 octet")
    return value


def _string_list(value: object, option: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise AutoconfConfigError(f"'{option}' must be a non-empty YAML list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise AutoconfConfigError(f"'{option}' entries must be non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(normalized) != len(set(normalized)):
        raise AutoconfConfigError(f"'{option}' must not contain duplicates")
    return normalized


def _non_empty_string(value: object, option: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AutoconfConfigError(f"'{option}' must be a non-empty string")
    return value.strip()


def _state_version(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{2}\.[0-9]{2}", value) is None:
        raise AutoconfConfigError(
            "'home.state_version' must be a quoted release such as '23.11'"
        )
    return value


@dataclass(frozen=True)
class AutoconfConfig:
    """Resolved options for one autoconf pipeline run."""

    source: Path
    ansible_root: Path
    output: Path
    nix_output: Path
    nix_templates: Path
    report_output: Path
    inventory_subnet: str
    inventory_system_group: str
    home_default_users: tuple[str, ...]
    home_state_version: str

    @classmethod
    def load(cls, source: Path | str | None = None) -> AutoconfConfig:
        config_source = DEFAULT_CONFIG_PATH if source is None else source
        source_path = Path(config_source).expanduser().resolve()
        if not source_path.is_file():
            raise AutoconfConfigError(f"Autoconf config not found: {source_path}")

        try:
            raw = load_unique_yaml_file(source_path)
        except yaml.YAMLError as exc:
            raise AutoconfConfigError(f"Invalid YAML in {source_path}: {exc}") from exc

        root = _mapping(raw, "root")
        _only_keys(root, {"schema_version", *_SECTION_KEYS}, "root")
        if root.get("schema_version") != 1:
            raise AutoconfConfigError("'schema_version' must be 1")

        paths = _required_section(root, "paths")
        inventory = _required_section(root, "inventory")
        home = _required_section(root, "home")

        base_dir = source_path.parent
        return cls(
            source=source_path,
            ansible_root=_relative_path(
                paths["ansible_root"], "paths.ansible_root", base_dir
            ),
            output=_relative_path(paths["output"], "paths.output", base_dir),
            nix_output=_relative_path(
                paths["nix_output"], "paths.nix_output", base_dir
            ),
            nix_templates=_relative_path(
                paths["nix_templates"], "paths.nix_templates", base_dir
            ),
            report_output=_relative_path(
                paths["report_output"], "paths.report_output", base_dir
            ),
            inventory_subnet=_subnet(inventory["subnet"]),
            inventory_system_group=_non_empty_string(
                inventory["system_group"], "inventory.system_group"
            ),
            home_default_users=_string_list(
                home["default_users"], "home.default_users"
            ),
            home_state_version=_state_version(home["state_version"]),
        )

    def validation_errors(self) -> list[str]:
        source = self.source_layout
        templates = self.template_layout
        required_files = {
            "Ansible inventory": source.inventory.hosts_file,
            "Home Manager host manifest": source.inventory.home_manifest,
        }
        required_directories = {
            "Nix system templates": templates.systems_dir,
        }
        errors = [
            f"{label} not found: {path}"
            for label, path in required_files.items()
            if not path.is_file()
        ]
        errors.extend(
            f"{label} not found: {path}"
            for label, path in required_directories.items()
            if not path.is_dir()
        )
        return errors

    @property
    def facts_dir(self) -> Path:
        """Directory containing local, sensitive Ansible fact snapshots."""
        return self.source_layout.facts_dir

    @property
    def source_layout(self) -> AutoconfSourceLayout:
        """Return all fixed inputs below the configured Ansible root."""
        return AutoconfSourceLayout(self.ansible_root)

    @property
    def output_layout(self) -> AutoconfOutputLayout:
        """Return all fixed artifact paths below the configured output root."""
        return AutoconfOutputLayout(self.output)

    @property
    def template_layout(self) -> NixTemplateLayout:
        """Return all fixed paths below the configured Nix template root."""
        return NixTemplateLayout(self.nix_templates)

    @property
    def nix_output_layout(self) -> NixOutputLayout:
        """Return all fixed paths below the configured Nix output root."""
        return NixOutputLayout(self.nix_output)

    @property
    def log_dir(self) -> Path:
        """Directory for logs produced by this configured pipeline run."""
        return self.output_layout.log_dir

    def require_valid(self) -> None:
        errors = self.validation_errors()
        if errors:
            raise AutoconfConfigError("\n".join(errors))

    def resolved_options(self) -> dict[str, Path | str]:
        """Return resolved values keyed by their canonical YAML option names."""
        return {name: self.get_option(name) for name in AUTOCONF_OPTION_NAMES}

    def get_option(self, name: str) -> Path | str:
        """Return one resolved option by its canonical YAML name."""
        try:
            field = _OPTION_FIELD_BY_NAME[name]
        except KeyError as error:
            choices = ", ".join(AUTOCONF_OPTION_NAMES)
            raise AutoconfConfigError(
                f"Unknown autoconf option '{name}'; choose from: {choices}"
            ) from error

        value = getattr(self, field)
        if isinstance(value, tuple):
            return ", ".join(value)
        return value

    def summary(self) -> str:
        lines = [f"config: {self.source}"]
        lines.extend(
            f"{option}: {value}" for option, value in self.resolved_options().items()
        )
        return "\n".join(lines)
