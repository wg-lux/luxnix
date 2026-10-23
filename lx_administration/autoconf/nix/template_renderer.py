"""Render Jinja templates with the shared LuxNix literal contract."""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_RAW_NIX_STRING_VALUES = {"true", "false", "null", "{}", "[]"}
_RAW_NIX_STRING_PREFIXES = (
    '"',
    "''",
    "'",
    "./",
    "../",
    "/",
    "pkgs.",
    "lib.",
    "config.",
    "inputs.",
    "{",
    "[",
    "(",
)


def _is_raw_nix_expression(value: str) -> bool:
    stripped = value.strip()
    if stripped in _RAW_NIX_STRING_VALUES:
        return True
    if re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", stripped):
        return True
    return stripped.startswith(_RAW_NIX_STRING_PREFIXES)


def _quote_nix_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def nix_string(value: str) -> str:
    """Serialize a value that is semantically required to remain a string."""
    if not isinstance(value, str):
        raise TypeError(f"Expected Nix string, got {type(value).__name__}")
    return _quote_nix_string(value)


def nix_literal(value: object) -> str:
    """Serialize supported configuration values as Nix expressions."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if "\n" in value:
            return _quote_nix_string(value)
        return value if _is_raw_nix_expression(value) else _quote_nix_string(value)
    if isinstance(value, list):
        return "[ " + " ".join(nix_literal(item) for item in value) + " ]"
    if isinstance(value, dict):
        assignments = [f"{key} = {nix_literal(item)};" for key, item in value.items()]
        return "{ " + " ".join(assignments) + " }"
    raise TypeError(f"Unsupported Nix literal type: {type(value).__name__}")


def render_nix_template(
    template_dir: str | Path,
    template_name: str,
    config_data: dict[str, object],
    *,
    filter_name: str = "nix",
    trim_blocks: bool = False,
    lstrip_blocks: bool = False,
) -> str:
    """Render one template using the shared Nix literal serializer."""
    environment = Environment(
        loader=FileSystemLoader(Path(template_dir)),
        undefined=StrictUndefined,
        trim_blocks=trim_blocks,
        lstrip_blocks=lstrip_blocks,
        autoescape=False,
    )
    environment.filters[filter_name] = nix_literal
    environment.filters["nix_string"] = nix_string
    template = environment.get_template(template_name)
    return template.render(**config_data)
